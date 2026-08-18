"""MCTP v0.1 — Core context transfer (hybrid delivery).

`build_packet` renders the hybrid handoff: always-provide high-value state (task,
decisions, entities) inline, and artifacts as **references** (path + hash + symbols) that
the receiver can retrieve on demand — never a lossy prose summary of code.

`flat_context` is the naive raw baseline: dump everything the source produced, expanding
artifacts to their FULL source, including stale (superseded/contradicted) state.
"""
from __future__ import annotations

from .store import Graph, MCTPStore

_SECTION = {"decision": "DECISIONS", "artifact": "ARTIFACTS (references — retrieve on demand)",
            "entity": "ENTITIES"}


def _artifact_line(n) -> str:
    r = n.ref or {}
    syms = ", ".join(r.get("symbols", [])) or "—"
    return (f"- [{n.id}] ({n.verification}) {r.get('path', n.content)} "
            f"[{r.get('language', '?')}] symbols: {syms} · hash:{r.get('hash', '?')[:8]} "
            f"· ~{r.get('tokens', '?')} tok · RETRIEVE {n.id} for full source")


def build_packet(graph: Graph, nodes, task_id: str) -> str:
    """Structured hybrid handoff packet."""
    task = graph.nodes[task_id]
    lines = [f"# TASK\n{task.content}"]

    by_type: dict[str, list] = {}
    for n in nodes:
        if n.id == task_id:
            continue
        by_type.setdefault(n.type, []).append(n)

    for t in ("decision", "artifact", "entity"):
        if t not in by_type:
            continue
        lines.append(f"\n# {_SECTION[t]}")
        for n in by_type[t]:
            if t == "artifact" and n.ref:
                lines.append(_artifact_line(n))
            else:
                lines.append(f"- [{n.id}] ({n.verification}) {n.content}")
    return "\n".join(lines)


def flat_context(store: MCTPStore) -> str:
    """Naive raw baseline: every asserted node, with artifacts expanded to full source,
    stale items included. This is the honest 'send everything' comparison."""
    graph = store.materialize()
    parts = []
    for ev in store.log:
        if ev.type != "node_asserted":
            continue
        n = graph.nodes.get(ev.payload["id"])
        if n and n.ref and n.ref["hash"] in graph.blobs:
            parts.append(f"{n.ref['path']}:\n{graph.blobs[n.ref['hash']]}")
        else:
            parts.append(ev.payload["content"])
    return "\n".join(parts)
