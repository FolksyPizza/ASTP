"""ASTP v0.1 — event-sourced store.

The append-only event log is the single source of truth. `materialize()` folds the log
into a graph (the "current state" view). Active/historical tiers and compaction are v0.2;
v0.1 keeps the whole log in memory and rebuilds the view on demand.
"""
from __future__ import annotations

from .model import (
    EVENT_TYPES,
    NODE_TYPES,
    RELATION_TYPES,
    Edge,
    Event,
    Node,
    Provenance,
    content_hash,
)


class Graph:
    """Materialized view: believed-state + audit flags."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self.blobs: dict[str, str] = {}   # content_hash -> source-of-truth bytes

    def retrieve_artifact(self, node_id: str) -> str:
        """Retrieve-on-demand: fetch the full source content behind an artifact node."""
        n = self.nodes.get(node_id)
        if n is None or not n.ref:
            raise KeyError(f"{node_id} is not a referenced artifact")
        h = n.ref["hash"]
        if h not in self.blobs:
            raise KeyError(f"blob {h} not stored")
        return self.blobs[h]

    def neighbors(self, node_id: str, relations=None, believed_only: bool = True):
        """Undirected 1-hop expansion. Returns (relation, node) pairs."""
        out = []
        for e in self.edges.values():
            if e.from_id != node_id and e.to_id != node_id:
                continue
            if relations and e.relation not in relations:
                continue
            other = e.to_id if e.from_id == node_id else e.from_id
            n = self.nodes.get(other)
            if n is None:
                continue
            if believed_only and not n.believed:
                continue
            out.append((e.relation, n))
        return out


class AstpStore:
    def __init__(self) -> None:
        self.log: list[Event] = []
        self._seq = 0

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def append(self, type: str, payload: dict, prov: Provenance) -> Event:
        if type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {type}")
        ev = Event(self._next(), type, payload, prov)
        self.log.append(ev)
        return ev

    # --- convenience emitters -------------------------------------------------
    def assert_node(self, node_id, node_type, content, prov, verification="asserted"):
        if node_type not in NODE_TYPES:
            raise ValueError(f"unknown node type: {node_type}")
        return self.append(
            "node_asserted",
            {"id": node_id, "node_type": node_type, "content": content,
             "verification": verification},
            prov,
        )

    def assert_artifact(self, node_id, path, content, language, symbols, prov,
                        descriptor=None, verification="asserted"):
        """Assert an artifact as a REFERENCE (path + content hash + language + symbols),
        storing the full source in the blob store for retrieve-on-demand. This replaces
        prose-summary artifacts, which lose implementation detail the receiver may need."""
        h = content_hash(path, content)
        self.append("blob_stored", {"hash": h, "content": content}, prov)
        ref = {"path": path, "hash": h, "language": language,
               "symbols": list(symbols), "tokens": max(1, len(content) // 4)}
        desc = descriptor or f"{path} [{language}]"
        return self.append(
            "node_asserted",
            {"id": node_id, "node_type": "artifact", "content": desc,
             "verification": verification, "ref": ref},
            prov,
        )

    def assert_edge(self, from_id, to_id, relation, prov):
        if relation not in RELATION_TYPES:
            raise ValueError(f"unknown relation: {relation}")
        eid = content_hash(from_id, relation, to_id)
        return self.append(
            "edge_asserted",
            {"id": eid, "from": from_id, "to": to_id, "relation": relation},
            prov,
        )

    def supersede(self, old_id, new_id, prov):
        """new_id supersedes old_id. old becomes not-believed; recorded as an edge too."""
        return self.append("node_superseded", {"old": old_id, "new": new_id}, prov)

    def contradict(self, node_id, reason, prov):
        return self.append("node_contradicted", {"id": node_id, "reason": reason}, prov)

    def verify(self, node_id, status, prov):
        return self.append("node_verified", {"id": node_id, "status": status}, prov)

    def record_transfer(self, task_id, node_ids, tokens, prov):
        """Audit-only: what packet was sent for which task."""
        return self.append(
            "transferred",
            {"task": task_id, "nodes": list(node_ids), "tokens": tokens},
            prov,
        )

    # --- materialization ------------------------------------------------------
    def materialize(self) -> Graph:
        g = Graph()
        for ev in self.log:
            p = ev.payload
            if ev.type == "node_asserted":
                g.nodes[p["id"]] = Node(
                    p["id"], p["node_type"], p["content"], ev.provenance,
                    verification=p.get("verification", "asserted"),
                    ref=p.get("ref"),
                )
            elif ev.type == "blob_stored":
                g.blobs[p["hash"]] = p["content"]
            elif ev.type == "edge_asserted":
                g.edges[p["id"]] = Edge(
                    p["id"], p["from"], p["to"], p["relation"], ev.provenance
                )
                self._apply_relation(g, p["from"], p["to"], p["relation"])
            elif ev.type == "node_superseded":
                new, old = p["new"], p["old"]
                eid = content_hash(new, "supersedes", old)
                g.edges[eid] = Edge(eid, new, old, "supersedes", ev.provenance)
                self._apply_relation(g, new, old, "supersedes")
            elif ev.type == "node_contradicted":
                n = g.nodes.get(p["id"])
                if n:
                    n.believed = False
                    n.verification = "contradicted"
            elif ev.type == "node_verified":
                n = g.nodes.get(p["id"])
                if n:
                    n.verification = p["status"]
            # retrieved / transferred are audit-only: no state change
        return g

    @staticmethod
    def _apply_relation(g: Graph, from_id: str, to_id: str, relation: str) -> None:
        if relation == "supersedes":
            old = g.nodes.get(to_id)
            if old:
                old.believed = False
                old.superseded_by = from_id
        elif relation == "contradicts":
            old = g.nodes.get(to_id)
            if old:
                old.believed = False
                old.verification = "contradicted"
