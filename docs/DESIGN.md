# MCTP Design

Design reference for the Model Context Transfer Protocol. It describes the goals, the
layering, the data model, the delivery strategy, the feedback interface used for evaluation,
and the roadmap. The wire and state schema is in [schema-v0.1.md](schema-v0.1.md); the
evaluation methodology and results are in [EXPERIMENTS.md](EXPERIMENTS.md).

## Goals and non-goals

MCTP represents the state a receiving model or agent needs to continue work, and transfers
that state rather than a raw conversation history. The objective is to preserve task success
while reducing the amount of context transferred; it is not primarily a compression system,
and lossless transfer is not a goal.

MCTP does not attempt to: solve AI memory in general; replace model reasoning; eliminate
retrieval; perfectly understand every task; replace human engineering judgment; guarantee
optimal or lossless context selection; create a universal AI architecture; or act as a
low-latency message bus.

It aims to: reduce unnecessary context transfer; preserve important state; improve agent
collaboration; improve auditability; and improve the cost/performance tradeoff.

## Layering: Core and Intelligence

MCTP is split into two layers so the protocol never depends on any learned component.

- Core MCTP (the protocol): state representation, memory storage, an audit log, retrieval
  including a deterministic cold-start selector, provenance, and context transfer. Core is
  fully usable with zero trained models.
- Intelligence Layer (optional, learned): context ranking, sufficiency prediction, retrieval
  planning, cost optimization, adaptive/predictive feeding. These sit on top of Core and only
  replace or augment the baseline selector's ranking.

Only Core is the portable protocol. MCTP-the-format and MCTP-the-selector-model are separable;
generalization across model families is claimed only for the format.

## Roles: extractor and selector

Two model roles are kept separate because they have different evaluation criteria and risk
profiles.

- Extractor (ingestion): turns raw agent context into structured MCTP nodes with provenance,
  incrementally as an agent works. Its recall is the ceiling on the whole system; anything it
  drops, the selector cannot recover.
- Selector (transfer/retrieval): given the materialized graph, a task, and a budget, returns a
  bounded packet of existing nodes. It is extractive (it chooses provenance-tagged nodes) so
  that every transferred item has a source and omissions are measurable.

Retrieval and handoff are the same operation with different seeds. Selection is a negotiation:
the system pushes a predicted-relevant packet and the receiver pulls more when it detects
insufficiency; the gap between push and pull is the training signal for the Intelligence Layer.

## Hybrid context delivery

The default packet composes three delivery tiers rather than choosing between a full dump and
an over-compressed summary:

- Always provide inline: high-value state — task objective, current state, active decisions,
  constraints, critical dependencies.
- Provide as references: artifacts (source files, docs, logs) as `{path, hash, language,
  symbols, dependencies}`, enough to locate and reason about without the bytes.
- Retrieve on demand: large or expensive content is fetched only when the receiver requests it
  (`RETRIEVE <id>`).

A targeted retrieve is expected behavior, not a miss; a fallback to the raw source for
something un-referenced is the miss. The selector may also refuse to compress when a task needs
global understanding, providing broader context instead.

## Data model

The semantic core that every adapter must round-trip losslessly:

```
node { id, type, provenance, payload }
edge { id, from, to, relation_type, provenance }
```

- Node types: `task`, `artifact`, `entity`, `decision`.
- Relation vocabulary (closed for v0.1): `calls`, `depends_on`, `modifies`, `supersedes`,
  `contradicts`, `derived_from`, `relates_to`.
- Identity: immutable artifacts are content-addressed; mutable conceptual nodes use a stable id
  with a version chain. Entities are anchored to `content-hash(artifact) + symbol locator`
  where possible, so two references to the same real thing resolve to the same id and the graph
  does not fragment.
- Provenance and trust: each node carries source, agent, model, timestamp, confidence, and a
  verification status (`asserted`, `tool-verified`, `human-verified`, `contradicted`).
  Convergence policy (which concurrent write survives) is decoupled from trust ranking (what the
  selector presents); the selector prefers verified state and surfaces contradictions rather
  than silently taking the newest.
- Retraction versus maintenance: invalidation ("this is now false") is a first-class
  `supersedes`/`contradicts` event; maintenance ("rarely used, demote") is a deterministic,
  threshold-based storage-tiering decision. Superseded or contradicted state is retained for
  audit but excluded from transfer by default.

## Storage

Three tiers, primarily to bound the search space: an active hot set searched first, a
historical tier searched on a miss, and an append-only audit log used for replay and
truth-enforcement (rarely read at retrieval time). Maintenance promotes, demotes, or archives
by a deterministic composite score (graph centrality, recency, frequency); information is
archived, not deleted. Scaling concerns include event-log compaction via snapshots, bounded
graph expansion for high-degree nodes, and incremental indexing.

## Feedback and observation interface

Each handoff produces one appended episode record, the unit of evaluation and the training
signal for the Intelligence Layer. No attention data is required; all signals are observable.

```
episode {
  scenario, condition, runner,
  context_tokens, packet_node_ids,
  retrieved_ids, retrieved_tokens,   # retrieve-on-demand pulls
  codebase_reads,                    # fallbacks to raw source not in the packet
  used_node_ids,                     # packet nodes referenced in output or actions
  outcome_pass, criteria, misleading
}
```

Behavioral signals map to labels: a pull is an INSUFFICIENT/recall signal for what the packet
omitted; a codebase read is a severe miss; a packet node with no evidence of use is an
AVAILABLE_UNUSED/precision cost; provided content that causes an incorrect claim is MISLEADING,
the costliest label and the target of staleness filtering and trust ranking. Recall labels come
from pulls and codebase-derived facts; precision labels come from packet nodes that were not
used.

## Evaluation

Correctness is the primary metric; token reduction matters only when task success is
maintained. Reported cost is total tokens including retrieval, never the initial packet alone.
Every episode records enough to reproduce it. The target is the best accuracy/cost tradeoff,
not the smallest possible context. Methodology and results are in [EXPERIMENTS.md](EXPERIMENTS.md);
the benchmark suite design is in the MCTP-Bench repository.

## Roadmap

- v0.1 (current): semantic-core schema, append-only event log, materialized current-state view,
  deterministic cold-start selector, artifact references with retrieve-on-demand, and an
  agent-handoff benchmark against a raw-transcript baseline.
- v0.2+: trained selector (the learning loop), three-tier storage and maintenance, adaptive
  feeding, abstractive bridge notes, multi-model adapters, a concurrency model, and security
  mitigations.
- v0.3: native integration, in which MCTP observes the agent environment, snapshots state, and
  delivers optimized context inline. Gated on the feedback/observation interface.

## Open questions

Foundational decisions taken for v0.1 include the identity and coreference scheme, the closed
relation vocabulary, retraction as a first-class event, the negotiation-based selection
contract, the decoupled trust model, and the benchmark fairness rules. Remaining research
questions include: how to measure extraction fidelity (the system's true ceiling); where MCTP's
own overhead breaks even against the context it saves; the concurrency model for concurrent
writers; retrieval reproducibility for audit; and the false-positive rate of adaptive feeding.

## Security

MCTP state is attacker-controllable input to the next model and persists across agents, so a
poisoned node is a stored prompt injection. Planned mitigations: treat MCTP content as data
rather than instructions, gate trust on provenance, sign provenance across trust boundaries,
enforce subgraph access control, and isolate namespaces across projects.
