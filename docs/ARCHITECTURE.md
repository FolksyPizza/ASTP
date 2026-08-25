# MCTP Architecture

How the Core reference implementation works, end to end. This document describes the actual
mechanics and code paths; for the design rationale and non-goals see [DESIGN.md](DESIGN.md),
and for the state/event schema see [schema-v0.1.md](schema-v0.1.md).

The Core implementation is in `core/mctp/`: `model.py` (types), `store.py` (event log and
materialized graph), `retrieval.py` (the selector), and `transfer.py` (packet construction).
It is dependency-free Python.

## Overview of the data flow

```
raw agent context
 │ assert_node / assert_artifact / assert_edge / supersede / contradict
 ▼
append-only event log ──materialize()──▶ Graph (nodes, edges, blobs, believed state)
 │ cold_start_select(task, budget)
 ▼
 selected subgraph
 │ build_packet(...)
 ▼
 hybrid packet (state inline + artifact references)
 │ receiver issues RETRIEVE <id>
 ▼
 retrieve_artifact(id) to full source (blob)
```

Everything is derived from the event log; the graph is a materialized view, never the source
of truth. This makes the same log replayable, auditable, and the basis for the audit trail.

## The event log

`MCTPStore` holds an ordered list of `Event` records, each with a monotonic `seq`, a `type`
from a closed set, a `payload`, and `Provenance` (source, agent, model, timestamp, confidence).
Events are appended through convenience methods rather than constructed directly:

- `assert_node(id, type, content, prov)`: record a task, entity, or decision node.
- `assert_artifact(id, path, content, language, symbols, prov)`, record an artifact as a
 reference and store its full source in the blob store (see below).
- `assert_edge(from, to, relation, prov)`: record a typed relation; the edge id is
 content-addressed from `(from, relation, to)` so the same relation asserted twice is one edge.
- `supersede(old, new, prov)` and `contradict(id, reason, prov)`, retraction events.
- `verify(id, status, prov)`: update a node's verification status.
- `record_transfer(...)`: audit-only; records which packet was sent for a task.

Node and relation types are closed vocabularies (`NODE_TYPES`, `RELATION_TYPES` in `model.py`):
node types are `task`, `artifact`, `entity`, `decision`; relations are `calls`, `depends_on`,
`modifies`, `supersedes`, `contradicts`, `derived_from`, `relates_to`. Closed sets keep the
graph walker, the adapters, and evaluation reproducible.

## Materialization and believed state

`MCTPStore.materialize()` folds the log into a `Graph` of `nodes`, `edges`, and `blobs` by
replaying events in order:

- `node_asserted` creates or replaces a `Node`.
- `edge_asserted` creates an `Edge` and, for `supersedes`/`contradicts`, applies the relation's
 side effect.
- `node_superseded` records a `supersedes` edge and marks the old node.
- `node_contradicted` marks the node.
- `blob_stored` records the full artifact source under its content hash.
- `retrieved`/`transferred` are audit-only and change no state.

The side effect of `supersedes` and `contradicts` (in `_apply_relation`) is to set the target
node's `believed = False`. A not-believed node is retained in the graph for audit but is
excluded from retrieval by default. This is how a superseded decision (for example, "use
distributed locking", later replaced by "use leases") stays in the record but is kept out of
transferred packets.

## Nodes, edges, and artifact references

A `Node` carries `id`, `type`, `content`, `provenance`, `verification`, `believed`,
`superseded_by`, and an optional `ref`. For task/entity/decision nodes, `content` is the text.
For artifacts, `content` is a short descriptor and `ref` holds the reference:

```
ref = { path, hash, language, symbols, tokens }
```

The full source lives in `Graph.blobs[hash]`, not in the node. This is the mechanism behind
hybrid delivery: a packet can carry the artifact's path, language, and symbols, enough to
locate and reason about it, without carrying the bytes, and the receiver fetches the bytes on
demand with `Graph.retrieve_artifact(id)`.

Artifact ids are content-addressed where they map to real files, so two references to the same
file resolve to the same node and the graph does not fragment.

## The selector

`cold_start_select(graph, task_id, budget_tokens=None, max_hops=3)` in `retrieval.py` is the
deterministic Core baseline; it uses no trained model. Its policy:

1. Seed the selection with the task node.
2. Expand outward up to `max_hops` over the graph, following edges through
 `Graph.neighbors(...)`, which returns only believed neighbors by default.
3. Skip other `task` nodes: so one task's scope does not pull in another's.
4. If a token budget is given: keep nodes in priority order, task, then decisions, then
 artifacts, then entities, dropping nodes that would exceed the budget.

Because expansion is over the believed subgraph, superseded and contradicted nodes are never
selected, and nodes belonging to unrelated tasks (which are not connected to the target task)
are not reached.

When the Intelligence Layer is enabled, selection becomes **semi-deterministic**: the
deterministic walk above produces a generous candidate set (favoring recall), and a trained
reranker scores and prunes it for the specific task and receiver, predicting sufficiency and
choosing what to inline versus reference. The learned model can only select from the candidate
set; it never invents content, so the packet stays extractive and auditable, and its
contribution is measurable as the delta over the deterministic baseline. The interface,
`select(graph, task, budget) -> [Node]`, is unchanged either way. The reranker is trained on the
episode labels the benchmark produces: nodes the receiver later pulled that were absent from the
packet are recall signal, and packet nodes it never used are precision signal.

Retrieval and handoff are the same operation with different seeds: retrieving "the auth code"
and handing off "continue the auth task" both reduce to selecting a bounded subgraph.

## Hybrid transfer

`build_packet(graph, nodes, task_id)` renders the selected nodes into the packet:

- The task node's content is the header.
- Decisions and entities are rendered inline with their id and verification status.
- Artifacts are rendered as reference lines, path, language, symbols, a short hash, an
 estimated token count, and a `RETRIEVE <id>` affordance, rather than inlined source.

The receiver reads the inline state, and when it needs an artifact's implementation it emits
`RETRIEVE <id>`; the host resolves that with `retrieve_artifact`. A targeted retrieve is
expected behavior. A fallback to the raw source for something that was not referenced at all is
the failure mode the design tries to avoid.

`flat_context(store)` renders the naive baseline used for comparison: every asserted node with
artifacts expanded to their full source and stale nodes included. This models a raw-transcript
handoff and is what the benchmark's `flat` condition uses.

## Auditing

The event log is the audit trail. Every assertion, retraction, verification, retrieval, and
transfer is an event with provenance, so the state at any point is reconstructable by replaying
the prefix of the log. `record_transfer` additionally logs exactly which nodes were sent for a
task, which, together with the receiver's later pulls, is the observable signal the evaluation
harness turns into recall/precision labels.

## How MCTP-Bench exercises this

The [MCTP-Bench](https://github.com/FolksyPizza/MCTP-Bench) harness builds a `Graph` per
scenario, then constructs two contexts: `flat` (the raw transcript) and `mctp` (the selector's
packet plus a retrievable blob map). A runner, a real model or the deterministic `MockRunner`
, answers from each context, and the run is scored into an episode record: context tokens,
retrieved tokens, total tokens, pulls, pass/fail, and whether any provided content was
misleading. Token counts are produced by real tokenizers (tiktoken encodings) with a chars/4
fallback. Methodology and results are in [EXPERIMENTS.md](EXPERIMENTS.md).
