"""ASTP v0.1 — core data model.

Everything is derived from an append-only event log (see store.py). These dataclasses
describe the *materialized* state and the events that produce it. Kept dependency-free.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Optional

# --- Closed vocabularies (v0.1) ------------------------------------------------
# Closed sets are required for the graph walker, eval reproducibility, and adapters.
NODE_TYPES = {"task", "artifact", "entity", "decision"}
RELATION_TYPES = {
    "calls",
    "depends_on",
    "modifies",
    "supersedes",
    "contradicts",
    "derived_from",
    "relates_to",
}
VERIFICATION = {"asserted", "tool-verified", "human-verified", "contradicted"}
EVENT_TYPES = {
    "node_asserted",
    "edge_asserted",
    "node_superseded",
    "node_contradicted",
    "node_verified",
    "blob_stored",   # source-of-truth artifact content, keyed by content hash
    "retrieved",     # audit-only (records a selection)
    "transferred",   # audit-only (records a handoff packet)
}


def content_hash(*parts: str) -> str:
    """Deterministic short id. Used for content-addressed artifacts and edge ids so
    that the same (from, relation, to) resolves to the same edge id by construction."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return digest[:16]


@dataclass
class Provenance:
    """Who/what/when asserted a piece of state. Descriptive by default; the selector
    may use `confidence`/verification for trust ranking (see Node.verification)."""
    source: str          # transcript | tool | human | ...
    agent: str           # which agent asserted it
    model: str           # which model produced it
    timestamp: int       # logical clock (monotonic per store)
    confidence: float = 1.0


@dataclass
class Event:
    """One entry in the append-only log. The log is the source of truth."""
    seq: int
    type: str
    payload: dict
    provenance: Provenance

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "type": self.type,
            "payload": self.payload,
            "provenance": asdict(self.provenance),
        }


@dataclass
class Node:
    """Materialized node. `believed` is False once superseded/contradicted — such nodes
    are excluded from retrieval by default but retained in history for audit."""
    id: str
    type: str
    content: str
    provenance: Provenance
    verification: str = "asserted"
    believed: bool = True
    superseded_by: Optional[str] = None
    # Artifacts carry a REFERENCE to source-of-truth content, not a prose summary:
    # {path, hash, language, symbols, tokens}. Full bytes live in the blob store and are
    # fetched on demand (hybrid delivery). None for non-artifact nodes.
    ref: Optional[dict] = None


@dataclass
class Edge:
    id: str
    from_id: str
    to_id: str
    relation: str
    provenance: Provenance
