# MCTP v0.1 — State & Event Schema

The event log is the **source of truth**. State (the graph) is a *materialized view* of
the log. This document is the normative reference; `core/mctp/` is the reference impl.

## Closed vocabularies

| Kind | Values |
|------|--------|
| Node types | `task`, `artifact`, `entity`, `decision` |
| Relation types | `calls`, `depends_on`, `modifies`, `supersedes`, `contradicts`, `derived_from`, `relates_to` |
| Verification | `asserted`, `tool-verified`, `human-verified`, `contradicted` |
| Event types | `node_asserted`, `edge_asserted`, `node_superseded`, `node_contradicted`, `node_verified`, `retrieved`, `transferred` |

Vocabularies are **closed** in v0.1 (extend deliberately, never with free text) so the
graph walker, adapters, and eval stay reproducible.

## Provenance (on every event)

```json
{ "source": "transcript|tool|human", "agent": "agent_A", "model": "model-x",
  "timestamp": 14, "confidence": 0.95 }
```

## Node (materialized)

```json
{ "id": "dec_handoff", "type": "decision", "content": "...",
  "verification": "tool-verified", "believed": true, "superseded_by": null,
  "provenance": { ... } }
```

- `believed` becomes `false` when a node is superseded or contradicted. Not-believed
  nodes are **excluded from retrieval by default** but retained for audit.
- `superseded_by` points to the replacing node.

## Edge (materialized)

```json
{ "id": "<hash(from,relation,to)>", "from": "art_nodetransfer",
  "to": "art_leasemanager", "relation": "depends_on", "provenance": { ... } }
```

Edge ids are content-addressed from `(from, relation, to)`, so the same relation asserted
twice resolves to one edge.

## Identity rules

- **Immutable artifacts** (files, tool outputs, evidence): content-addressed id.
- **Mutable conceptual nodes** (task, decision, entity): stable id + version via
  `supersedes`.
- **Entity coreference**: where an entity maps to a real artifact, derive its id from
  `content-hash(artifact) + symbol locator` so two references resolve to the same id by
  construction. Purely abstract entities fall back to fuzzy resolution.

## Events

| Event | Payload | Effect on view |
|-------|---------|----------------|
| `node_asserted` | `{id, node_type, content, verification}` | create/replace node |
| `edge_asserted` | `{id, from, to, relation}` | create edge; `supersedes`/`contradicts` flip target `believed=false` |
| `node_superseded` | `{old, new}` | add `supersedes` edge; `old.believed=false` |
| `node_contradicted` | `{id, reason}` | `believed=false`, `verification=contradicted` |
| `node_verified` | `{id, status}` | set `verification` |
| `retrieved` | `{task, nodes}` | audit-only |
| `transferred` | `{task, nodes, tokens}` | audit-only |

## Retrieval contract (Core baseline)

```
select(graph, task_id, budget_tokens?, max_hops=3) -> [Node]
```

Deterministic bounded k-hop expansion over the **believed** subgraph around the task,
excluding other tasks, then budget-bounded by type priority (task → decision → artifact →
entity). The Intelligence Layer replaces the ranking; the *contract* stays fixed.
