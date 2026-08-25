# MCTP Primer

A plain-language guide to what MCTP is and how it works, for readers who are new to the ideas.
It defines the jargon as it goes. For the precise mechanics see [ARCHITECTURE.md](ARCHITECTURE.md);
for the design rationale see [DESIGN.md](DESIGN.md).

## The problem MCTP is trying to solve

AI "agents" are language models that do multi-step work, read files, run tools, make decisions.
Often one agent needs to hand its work to another (a bigger model, a specialist, or a fresh
agent after the first one filled up its memory). The question is: **what do you give the second
agent so it can continue?**

Two common answers, and why each is imperfect:

- **The transcript**: send the entire history of everything the first agent saw and did. Nothing
 is lost, but it's huge, full of dead ends and outdated decisions, and expensive for the next
 model to read.
- **A summary**: have a model write a short version. Smaller, but a second model now decides
 what matters, and it can drop something critical or keep something misleading, and you lose the
 exact original material.

MCTP is a third answer: **keep the complete state, but only send what's relevant now, and let the
receiver fetch the original details on demand.**

## The core idea in one picture

```
Agent A's work ──▶ MCTP builds a structured "map" of the state ──▶ send only the relevant part
 │
 └──▶ the full detail stays stored, fetchable on request
```

MCTP's motto: **preserve everything, propagate selectively, retrieve precisely.**

## What "structured state" means: nodes and edges

MCTP stores state as a **graph**. A graph is just **things (nodes)** connected by **relationships
(edges)**. If you've seen a diagram of boxes joined by arrows, that's a graph.

- **Nodes** are the important things. MCTP has four kinds:
 - **Task**: what needs doing ("fix the duplicate-charge bug").
 - **Decision**: a choice that was made, and why ("use idempotency keys, not a lock").
 - **Artifact**: a file, log, or document (referenced, not pasted in full, more below).
 - **Entity**: a concept or component ("the idempotency key").
- **Edges** are the relationships, and they're *labeled*. A few labels MCTP uses:
 - `depends_on`: `calls`, `modifies`, structural links between code/components.
 - `supersedes`: one decision replaces an earlier one (D replaces C).
 - `relates_to`: `derived_from`, softer connections.

Because the relationships are explicit and labeled, the system can *follow* them instead of
guessing. That's the whole trick.

## Call graphs (a concrete kind of graph)

You asked specifically about call graphs, and they're a good example.

A **call graph** is a map of which functions call which other functions. If `charge()` calls
`create()`, and `create()` calls `authorizeAndCapture()`, the call graph has arrows
`charge to create to authorizeAndCapture`. Programmers use call graphs to answer "if I change this
function, what else is affected?"

MCTP uses the same idea with its `calls` and `depends_on` edges. When the task is "change
`charge()`," the system can walk those edges to pull in exactly the functions and files that
`charge()` touches, and skip the thousands of unrelated files. That's *far* more precise than
searching text for the word "charge." The graph knows the real structure, so it can gather the
truly relevant neighborhood instead of things that merely look similar.

## How the state is stored: an event log

MCTP never edits state in place. Instead it keeps an **append-only event log**, a list of small
records like "asserted this node," "added this edge," "this decision supersedes that one." To get
the *current* picture, it **replays** the log from the start and folds the events together. This
is called **event sourcing**.

Why do it this way?

- **History is free.** Nothing is overwritten, so you can always see how the state got here.
- **Auditability.** Every fact has a source (who/what/when added it), that's **provenance**.
- **Superseding, not deleting.** When a decision is replaced, the old one is *marked* superseded,
 not erased. It stays for the record but is left out of what gets sent onward.

## How MCTP decides what to send: the selector

When it's time to hand off, MCTP runs the **selector**. Today the Core selector is a simple,
deterministic rule: start at the task node and **walk outward along the edges** a few steps,
collecting the connected decisions, files, and concepts, while skipping anything that's been
superseded. Then it trims to a size budget.

"Deterministic" means there's no AI and no randomness here: the same graph and task always
produce the same result, and you can point to the exact edge that pulled in each piece. It's
cheap, instant, and explainable. Its weakness is that it only knows what the *edges* tell it, if
the graph doesn't connect something to the task, the selector can't find it.

## References and retrieve-on-demand

The selector doesn't paste whole files into the handoff. Instead, an artifact is sent as a
**reference**: its path, a content hash, its language, and the names of the functions in it
(its "symbols"). That's usually enough for the receiver to reason about it.

If the receiver actually needs the full source, it asks, it emits `RETRIEVE <id>`, and MCTP
returns the exact original bytes from storage. This is **retrieve-on-demand**. A targeted fetch
is normal, expected behavior, not a failure. The point is that the heavy content isn't shipped
unless it's needed.

## Transcript vs. summary vs. MCTP, in plain terms

- **Transcript:** "Here is absolutely everything. You sort it out."
- **Summary:** "Another model read it and decided what you should know."
- **MCTP:** "Everything is preserved. Here is the part that matters for your task right now, and
 the original evidence is one request away if you need it."

## Two places an AI model fits (and two places it doesn't)

A natural question: if MCTP is for AI agents, where are the AI models?

- **The extractor** (turns raw agent activity into the graph) *is* a model's job, it has to
 understand the work well enough to draw the right nodes and edges. Its accuracy is the ceiling
 on everything else: if it links a fact to the wrong place, the selector can't recover it.
- **The selector's ranking** *can* be a model, but doesn't have to be. Today it's the
 deterministic walk. The plan is **semi-deterministic**: the deterministic walk gathers a
 generous, auditable set of candidates, and a small trained model then **ranks and prunes** them
 for the specific task and receiver. Crucially, that model can only *choose from* real candidates
, it can't invent anything, so the result stays trustworthy and traceable.
- **Storing and fetching** are always plain, deterministic mechanics, no model needed.

So the "intelligence" is in building a good map (the extractor) and, optionally, in choosing
smartly from it (the learned ranker), while the protocol underneath stays simple, reproducible,
and inspectable.

## How we know if it works

MCTP is a research prototype. It's evaluated by having a second agent actually do the task from
each kind of handoff (transcript, summary, MCTP) and checking two things: **did the task
succeed** (judged by the benchmark's own tests), and **at what cost** (tokens sent, extra
fetches, reliability across repeated runs). The current status and numbers are in
[EXPERIMENTS.md](EXPERIMENTS.md), including a case where MCTP *fails*, which is kept on purpose.
