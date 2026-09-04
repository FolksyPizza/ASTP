# Agent State Transfer Protocol

ASTP is a protocol for carrying agent state across handoffs: between the agents of a swarm, or
between models in a chain. Instead of passing an entire conversation history from one agent to the
next, ASTP represents the important state explicitly, hands off the high-value current state,
references deeper artifacts, and retrieves their details only when they are needed.

ASTP is built for multi-agent workflows, where the same state passes through many hands. It is not
primarily a compression system; it separates persistent agent state from active model context.
Its operating principle is *preserve everything, propagate selectively, retrieve precisely*: the
complete state (decisions, constraints, artifacts, provenance, and superseded approaches) is
stored and auditable, only the relevant current state is handed to the next agent, and the
original evidence stays retrievable on demand.

## Overview

Agent swarms and model-to-model chains hand off work as raw transcripts or free-text summaries.
Both degrade as the work passes through more agents. A transcript grows with the whole accumulated
history until it strains or overflows the context window, and it drags along stale content
(abandoned approaches, superseded decisions). A summary re-interprets the state at every hop,
drifting and dropping the provenance and detail the next agent needs. ASTP instead hands off an
explicit, provenance-tracked representation of the current state that stays compact and accurate
across an arbitrary number of handoffs, with the original source material available on demand.

This is where the advantage is structural rather than incidental. A summary cannot preserve which
agent established a fact and whether it was later superseded, and plain retrieval has no state
model at all. Only an explicit, event-sourced believed-state survives a chain of handoffs intact,
which is why the multi-agent case, not context reduction on a single turn, is the protocol's
central claim. See [docs/SWARMS.md](docs/SWARMS.md) for why this holds across a deep chain of
handoffs where transcript and summary degrade.

Scope is deliberately limited. ASTP does not attempt to solve AI memory in general, does not
replace retrieval, and does not guarantee optimal context selection. See
[docs/DESIGN.md](docs/DESIGN.md) for the full list of non-goals.

## Transcript vs. summary vs. ASTP

Three ways to hand work from one agent to the next:

- **Transcript** sends everything: "here is all of it, you figure it out."
- **Summary** sends an interpretation: "another model decided what you should know."
- **ASTP** preserves everything, sends the relevant current state, and keeps the underlying
  evidence retrievable on demand.

| | Transcript | Summary | ASTP |
|---|---|---|---|
| What the receiver gets | The full history | An LLM's condensed interpretation | Selected current-state nodes plus artifact references |
| Extra inference to prepare it | None | A summarization call (its cost must be counted) | None (deterministic selection) |
| Stale / superseded content | Included as-is | May keep or drop it, unpredictably | Excluded from the packet; retained in state and marked superseded |
| Provenance and exact source | Present but unstructured | Usually lost | Explicit and structured (source, agent, supersession) |
| Underlying information after handoff | Still in the transcript | Lost if the summary dropped it | Preserved and retrievable (`RETRIEVE <id>`) |
| Risk of omitting a critical fact | Low (it sends everything) | Real (the model may drop it) | Real only if the fact is not linked to the task (extraction fidelity is the ceiling) |
| Cost as history accumulates | Grows with the whole history | Re-summarize repeatedly | Active context stays small; state is stored separately |
| Structured / auditable | No | No | Yes |
| Built for agent-to-agent handoff | No | No | Yes |

The evaluation treats transcript, summary (counting the summarizer's inference), conventional
retrieval (RAG), and ASTP as separate baselines; see the
[benchmark design](https://github.com/FolksyPizza/ASTP-Bench/blob/main/docs/BENCHMARK.md).

## Architecture

ASTP is organized into three layers.

1. State layer: the explicit, high-value context that is always transferred, comprising goals,
   decisions (including rejected alternatives and supersession), constraints, and dependencies.
   Superseded or contradicted state is retained for audit but excluded from transfer by default.
2. Artifact layer: files, code, documents, and logs are represented as references
   (`path`, content hash, language, symbols, dependencies) rather than inlined summaries. The
   full source of truth is stored and fetched on demand.
3. Retrieval layer: deeper information is retrieved only when the receiver requests it
   (`RETRIEVE <id>`), so large or expensive content is not transferred pre-emptively.

Together these implement hybrid context delivery: always provide high-value state inline,
provide artifacts as references, and retrieve heavy content on demand.

The protocol is split into a Core layer (state representation, storage, audit log, retrieval,
provenance, transfer, usable with no trained models) and an optional Intelligence Layer
(learned ranking, sufficiency prediction, adaptive feeding). Only Core is the portable
protocol. See [docs/DESIGN.md](docs/DESIGN.md).

## Repository layout

```
core/astp/     Core reference implementation (event-sourced store, selector, transfer)
docs/          PRIMER.md (start here), DESIGN.md (rationale), ARCHITECTURE.md (mechanics),
               ROADMAP.md, schema-v0.1.md, EXPERIMENTS.md, RESEARCH-LOG.md
bench/         local viability probe and handoff example
intelligence/  optional Intelligence Layer (design notes)
```

The evaluation harness lives in the companion repository
[ASTP-Bench](https://github.com/FolksyPizza/ASTP-Bench).

## Current results

These are interim results from a large-scale run: one capable model over the standard suites, at
a single trial per task. The model is a 27B-parameter open-weights model (Qwen3 series, 4-bit
quantized) served with a 128K context window, run under four conditions: `transcript` (the full
accumulated context), `summary` (same-model summarization), `rag` (TF-IDF retrieval), and `mctp`
(a believed-state packet selected to a token budget). Task success is an objective check:
executed unit tests for the code suites, exact-match answers otherwise. Each cell reports the
pass rate and the average delivered-context size in tokens (tiktoken `o200k_base`).

| Suite | transcript | summary | rag | mctp |
| --- | --- | --- | --- | --- |
| gsm8k | 97% / 0 | 97% / 0 | 97% / 0 | 97% / 63 |
| humaneval | 96% / 0 | 96% / 0 | 96% / 0 | 96% / 136 |
| mbpp | 82% / 0 | 82% / 0 | 82% / 0 | 81% / 52 |
| multifile | 100% / 80 | 91% / 279 | 100% / 75 | 100% / 157 |
| longbench | 61% / 12,360 | 46% / 836 | 46% / 354 | 59% / 180 |

Cells are pass rate / average context tokens.

On the low-context suites (gsm8k, humaneval, mbpp) the four conditions fall within a point of each
other. These tasks carry little prunable context, so the delivery method does not change the
outcome; ASTP does not cost accuracy where there is nothing to select.

The long-context suite is where the delivery method separates. On longbench, ASTP nearly matches
the full transcript (59% against 61%) while delivering about one sixty-ninth of the context
(180 tokens against 12,360), and it scores about thirteen points above both same-model
summarization and TF-IDF retrieval. On the smaller models, whose 8192-token window forces the
transcript to truncate, ASTP wins outright. That is the intended result: the accuracy of sending
everything at a fraction of the token cost.

The repobench, swebench, and multi-agent (swarm) suites are still being finalized and are not yet
reported. Full methodology and the per-suite tables are in the ASTP-Bench
[results doc](https://github.com/FolksyPizza/ASTP-Bench/blob/main/docs/RESULTS.md).

## Limitations

- Results are interim: one capable open-weights model and two small models so far, at a single
  trial for the large model. Broader model coverage, more trials, and the deferred cross-review
  judge pass are in progress.
- Two suites are not yet reportable: repobench pending a completion-prompt fix, and swebench
  pending native test-verified scoring.
- The clearest wins are on long-context and multi-agent handoffs. On cold-start, low-context
  tasks ASTP neither helps nor hurts, as expected when there is nothing to select.
- Scoring is automated (execution for code, robust answer matching for QA); human validation is
  in progress through the review tooling, and a deferred judge pass will add graded review.
- The believed-state graphs for the synthetic suites are built by the adapters, not produced by a
  general extractor. Extractor quality is future work and is the ceiling on real-world use.

## Roadmap

Approximate targets for a research prototype, not commitments; dates may move as results come in.

- **Now (Sep 2026):** the Core reference implementation and the ASTP-Bench harness are complete,
  and the large-scale open-model run is underway across the suites (code, math, repository,
  long-context, and multi-agent). Interim results are published, QA scoring is robust to
  formatting and rewording, and a local full-audit review app supports human grading and flagging.
- **Next (the headline direction):** the multi-agent swarm evaluation with pipeline depth (3, 5,
  and 8 handoffs) and cross-family arrangements, where a carried decision must survive every hop.
  This is where ASTP's believed-state is expected to separate from summary and retrieval, which
  cannot track state across handoffs.
- **Also next:** complete the capable-model sweep, fix the repobench and swebench scoring, add
  native SWE-bench test-verified scoring, and run the deferred cross-review judge pass.
- **Then:** retrieval-augmented selection (`mctp-r`) evaluated head to head, and Intelligence Layer
  v0.1, the learned selector and reranker (synthetic data; see
  [docs/MODEL-CARD.md](docs/MODEL-CARD.md)), reported against the deterministic Core baseline.
- **Beyond:** adaptive context feeding, larger multi-agent swarm evaluation, and schema v0.2.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the detailed phase plan.

## Status

Research prototype under active development. Interfaces and schema are versioned at v0.1 and
may change.
