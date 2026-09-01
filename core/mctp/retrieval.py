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


def cold_start_select(graph: Graph, task_id: str, budget_tokens=None, max_hops: int = 3,
                      relevance=None):
    """Return the baseline packet (list of Nodes) for continuing `task_id`.

    Selection is a bounded k-hop walk of the believed subgraph around the task, excluding other
    tasks and superseded/contradicted nodes. Nodes are then ranked for transfer by (type priority,
    hop distance): load-bearing state first (task, then decisions), nearer nodes before farther —
    so when a `budget_tokens` cap forces a choice, the packet keeps the closest, most load-bearing
    context and sheds distant, peripheral nodes (typically entities several hops out). This makes
    the packet tunable to the receiver's context window: a tight budget yields a focused packet, a
    generous one includes more of the neighborhood. The task node is always retained. Passing no
    budget returns the full k-hop neighborhood (the original behavior).

    `relevance`, if given, is a callable `node -> float` scoring how relevant a node's content is
    to the task query. When present and a budget applies, the packet still guarantees the load-
    bearing state (the task and every decision node, provenance that a pure retriever cannot
    reconstruct), then fills the remaining budget with the supporting artifacts and entities
    ranked by relevance rather than by hop distance. This is retrieval inside MCTP: the structural
    guarantee of believed-state with the precision of relevance-scored selection."""
    if task_id not in graph.nodes:
        raise KeyError(f"unknown task node: {task_id}")

    hop_of = {task_id: 0}
    selected = {task_id: graph.nodes[task_id]}
    frontier = [task_id]
    for hop in range(1, max_hops + 1):
        nxt = []
        for nid in frontier:
            for _rel, n in graph.neighbors(nid, believed_only=True):
                if n.type == "task":          # don't pull other tasks' scope in
                    continue
                if n.id in selected:
                    continue
                selected[n.id] = n
                hop_of[n.id] = hop
                nxt.append(n.id)
        frontier = nxt
        if not frontier:
            break

    # Rank: state before artifacts before entities; within a type, nearer the task first.
    nodes = sorted(selected.values(),
                   key=lambda n: (_TYPE_ORDER.get(n.type, 9), hop_of.get(n.id, 99)))

    if budget_tokens is not None:
        task_node = graph.nodes[task_id]
        kept, used = [task_node], estimate_tokens(task_node.content)
        others = [n for n in nodes if n.id != task_id]
        if relevance is not None:
            # Load-bearing state stays (decisions, nearest first); the rest fills the remaining
            # budget by relevance to the task instead of by hop distance.
            decisions = [n for n in others if n.type == "decision"]
            support = [n for n in others if n.type != "decision"]
            support.sort(key=lambda n: relevance(n), reverse=True)
            others = decisions + support
        for n in others:
            t = estimate_tokens(n.content)
            if used + t > budget_tokens:
                continue                       # skip this node, keep trying smaller later ones
            kept.append(n)
            used += t
        nodes = kept
    return nodes
