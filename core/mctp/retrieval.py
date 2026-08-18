"""MCTP v0.1 — Core retrieval / cold-start selector.

This is the *deterministic baseline* the Intelligence Layer later replaces/augments with
a learned ranker. It exists so Core is fully usable with zero trained models.

Baseline policy: bounded k-hop expansion of the believed subgraph around the task,
excluding other tasks and any not-believed (superseded/contradicted) node, then
budget-bounded by node type priority. It is intentionally simple and over-includes at the
edges — closing that precision gap is exactly the Intelligence Layer's job.
"""
from __future__ import annotations

from .store import Graph

# Priority when trimming to a token budget: task/decisions are load-bearing, entities last.
_TYPE_ORDER = {"task": 0, "decision": 1, "artifact": 2, "entity": 3}


def estimate_tokens(text: str) -> int:
    """Cheap, model-agnostic token estimate (~4 chars/token). Good enough for a probe;
    swap for a real tokenizer in MCTP-Bench."""
    return max(1, len(text) // 4)


def cold_start_select(graph: Graph, task_id: str, budget_tokens=None, max_hops: int = 3):
    """Return the baseline packet (list of Nodes) for continuing `task_id`."""
    if task_id not in graph.nodes:
        raise KeyError(f"unknown task node: {task_id}")

    selected = {task_id: graph.nodes[task_id]}
    frontier = [task_id]
    for _ in range(max_hops):
        nxt = []
        for nid in frontier:
            for _rel, n in graph.neighbors(nid, believed_only=True):
                if n.type == "task":          # don't pull other tasks' scope in
                    continue
                if n.id in selected:
                    continue
                selected[n.id] = n
                nxt.append(n.id)
        frontier = nxt
        if not frontier:
            break

    nodes = sorted(selected.values(), key=lambda n: _TYPE_ORDER.get(n.type, 9))

    if budget_tokens is not None:
        kept, used = [], 0
        for n in nodes:
            t = estimate_tokens(n.content)
            if used + t > budget_tokens:
                continue
            kept.append(n)
            used += t
        nodes = kept
    return nodes
