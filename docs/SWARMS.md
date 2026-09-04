# Multi-agent handoffs: why ASTP

ASTP's central claim is not that it compresses context on a single turn. It is that an explicit,
provenance-tracked believed-state survives a chain of handoffs where the two common alternatives,
raw transcript and free-text summary, degrade. This document explains the mechanism and why the
advantage is structural rather than incidental.

## The setting

In an agent swarm, one unit of work passes through many agents in sequence: a researcher, an
architect, an implementer, a reviewer, a tester, and so on. Each agent receives the state
accumulated so far, does its part, and hands the result to the next. The question is how that
accumulated state is represented at each handoff. There are three answers.

- **Transcript**: hand the next agent the full running history.
- **Summary**: have a model condense the history into prose at each hop.
- **ASTP**: hand over the current believed-state as structured nodes with provenance, and keep the
  underlying evidence retrievable on demand.

The difference between them is small at one hop and grows with every additional hop. A swarm is
precisely the case where the number of hops is large.

## How the baselines degrade with depth

**Transcript grows without bound.** Every hop appends the previous agent's output, so after N
agents the transcript is the sum of all work done so far. Two failures follow. First, cost scales
with the whole history, not with what the next agent needs. Second, and worse, the transcript
eventually exceeds the receiver's context window, at which point it is truncated. Truncation is
blind: it drops whichever tokens fall outside the window, which are often the early decisions and
constraints that later stages still depend on. The transcript also carries stale content, the
abandoned approaches and superseded decisions, with no marking to tell the receiver which parts
are still live.

**Summary drifts.** Re-summarizing at each hop is a telephone game. A summary is an interpretation,
and interpreting an interpretation compounds error: specific values get rounded off, qualifiers are
dropped, and the provenance of a fact, which agent established it and whether it was later
overridden, is lost almost immediately. A detail that a stage-8 agent needs may have been dropped
by the stage-2 summary and cannot be recovered, because the summary replaced the source rather than
referencing it.

## Why ASTP holds

ASTP hands off the materialized believed-state: the current, non-superseded nodes selected around
the receiving task, within a token budget, with artifacts as references. Four properties make this
survive a deep chain.

1. **Bounded size.** The packet is budget-bounded regardless of how many hops preceded it. Hop 8
   costs the same as hop 1, because the packet carries current state, not accumulated history. There
   is no growth curve to overflow.
2. **Preserved provenance.** State is carried as structured facts, each tagged with the agent that
   asserted it and a sequence position. A decision established at hop 0 is present verbatim at hop 8,
   still attributable. There is no re-interpretation step to drift through.
3. **Explicit supersession.** When a later agent overrides an earlier decision, ASTP marks the old
   node superseded and transfers only the current one. A transcript keeps both and makes the receiver
   infer which is live; a summary keeps one unpredictably. ASTP removes the ambiguity.
4. **Auditability.** Because the transfer is structured, you can inspect exactly what state crossed
   each handoff and why a node was included or dropped. A prose blob or a summary cannot be inspected
   that way.

The underlying evidence is not lost in exchange for this compactness. Artifacts travel as references
(`RETRIEVE <id>`) backed by a content-addressed store, so any stage can pull the full source of a
file or document on demand without it having been pushed through every prior hop.

## A concrete example

Suppose the architect at stage 0 establishes a mandatory design decision: identifiers use an
underscore separator, not a hyphen. Several unrelated stages follow (documentation, a review, a
test plan) before an implementer at the final stage writes the code.

- **Transcript**: the decision is near the top of a long history. A capable model with a large
  window can still find it, but at growing token cost, and on a smaller window the decision may have
  been truncated away.
- **Summary**: the intervening summaries, focused on their own stages, are likely to have dropped a
  one-line formatting decision. The implementer never sees it.
- **ASTP**: the decision is a `decision` node with provenance. It is load-bearing, so the selector
  keeps it in the packet handed to the implementer, compactly and intact, regardless of how many
  stages intervened.

The implementer honors the decision under ASTP, may or may not under transcript depending on window
size, and typically cannot under summary.

## How this is measured

The `swarm` suite in ASTP-Bench operationalizes exactly this. Each task is a pipeline where a
carried design decision is set at the first stage and only checked at the final stage, with
distractor stages padding the pipeline to depths of 3, 5, and 8 handoffs. Every stage runs under
each condition (transcript, summary, rag, mctp), threading that condition's own representation of
state forward, and each stage is recorded separately so the per-hop token cost is captured. The
final stage carries the objective check: did the carried decision survive.

The expected signal is a slope, not a point. Transcript preserves the decision but at a token cost
that rises with depth and eventually truncates on a bounded window; summary loses it with
increasing frequency as depth grows; ASTP holds both accuracy and a flat token cost across depth.
The advantage should therefore widen as the pipeline lengthens, which is the property a swarm
stresses and a single handoff does not.

## Summary

Transcript is complete but unbounded and unstructured; summary is compact but lossy and
un-auditable. ASTP is the only one of the three that is at once compact, complete (via
retrieve-on-demand), provenance-preserving, and auditable, and those are the properties a chain of
handoffs demands. That is why the multi-agent case, rather than single-turn context reduction, is
the protocol's central claim.
