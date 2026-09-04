"""A small but realistic handoff scenario for the viability probe.

Story (a Minecraft Folia example):
  - Agent A investigated intermittent data loss during partition migration (bug #43).
  - A explored an unrelated subsystem earlier, and A's FIRST decision (distributed
    locking) was later SUPERSEDED by a leasing decision after latency testing.
  - Agent B must now implement the lease-based fix in NodeTransfer.

The graph deliberately contains an entire irrelevant subsystem (biome rendering) and a
superseded decision, so the probe can show that ASTP transfer (a) excludes irrelevant
state and (b) never ships the stale decision — which a flat dump does.
"""
from __future__ import annotations

from mctp import AstpStore, Provenance


def _p(agent="agent_A", model="model-x", ts=0, source="transcript", conf=1.0):
    return Provenance(source=source, agent=agent, model=model, timestamp=ts, confidence=conf)


def build_scenario() -> tuple[AstpStore, str]:
    """Return (store, handoff_task_id) for Agent B's continuation."""
    s = AstpStore()

    # --- Tasks ----------------------------------------------------------------
    s.assert_node("task_A", "task",
        "Investigate intermittent data loss during partition migration under load "
        "(bug #43). Reproduced only when a partition migrates while its owner is still "
        "serving writes.", _p(ts=1))
    s.assert_node("task_B", "task",
        "Take over bug #43: fix the intermittent data loss during partition migration in "
        "NodeTransfer.", _p(ts=2))
    s.assert_node("task_C", "task",
        "Optimize biome rendering performance in the client renderer.", _p(agent="agent_Z", ts=3))

    # --- Artifacts (code files carry REAL source via assert_artifact) ---------
    s.assert_artifact("art_nodetransfer", "src/shard/NodeTransfer.java",
        "public final class NodeTransfer {\n"
        "  private final PartitionMap map;\n"
        "  private final LeaseManager leases;\n"
        "  void migrate(PartitionId pid, ShardId from) {\n"
        "    Owner owner = map.ownerOf(pid);\n"
        "    copyNodeState(pid, from);      // BUG: copies BEFORE confirming ownership\n"
        "    map.setOwner(pid, self);\n"
        "  }\n"
        "  private void copyNodeState(PartitionId pid, ShardId from) { /* streams state */ }\n"
        "}\n",
        "java", ["migrate(PartitionId, ShardId)", "copyNodeState(PartitionId, ShardId)"], _p(ts=4))
    s.assert_artifact("art_leasemanager", "src/shard/LeaseManager.java",
        "public final class LeaseManager {\n"
        "  public boolean isOwner(PartitionId pid) { ... }\n"
        "  public void renew(PartitionId pid, Duration ttl) { ... }\n"
        "}\n",
        "java", ["isOwner(PartitionId)", "renew(PartitionId, Duration)"], _p(ts=5))
    s.assert_artifact("art_partitionmap", "src/shard/PartitionMap.java",
        "public final class PartitionMap {\n"
        "  Owner ownerOf(PartitionId pid) { ... }\n"
        "  void setOwner(PartitionId pid, ShardId s) { ... }\n"
        "}\n",
        "java", ["ownerOf(PartitionId)", "setOwner(PartitionId, ShardId)"], _p(ts=6))
    # bug report is evidence, not code -> stays a content node
    s.assert_node("art_bug43", "artifact",
        "Bug report #43: under load, destination shard begins copying while source shard "
        "still accepts writes; last writes are lost. Timing-dependent.", _p(ts=7))
    # irrelevant subsystem
    s.assert_artifact("art_biome", "src/client/BiomeRenderer.java",
        "public final class BiomeRenderer { void buildMesh(Chunk c) { /* greedy meshing */ } }\n",
        "java", ["buildMesh(Chunk)"], _p(agent="agent_Z", ts=8))

    # --- Entities -------------------------------------------------------------
    s.assert_node("ent_lease", "entity",
        "Lease ownership model: a partition is owned via a time-bounded lease; writes are "
        "only valid while the lease is held and unexpired.", _p(ts=9))
    s.assert_node("ent_partition", "entity",
        "PartitionManager: coordinates partition assignment and migration across shards.",
        _p(ts=10))
    s.assert_node("ent_biome", "entity",
        "Greedy meshing: merges adjacent faces to reduce vertex count when rendering biomes.",
        _p(agent="agent_Z", ts=11))

    # --- Decisions ------------------------------------------------------------
    # A's FIRST decision, later superseded:
    s.assert_node("dec_locking", "decision",
        "Use distributed locking for partition ownership during migration.", _p(ts=12))
    # the decision that supersedes it:
    s.assert_node("dec_leases", "decision",
        "Use time-bounded leases instead of distributed locking for ownership. Reason: "
        "latency testing showed lock contention stalled migrations under load. Evidence: "
        "benchmark run bench/lock_vs_lease.json.", _p(ts=13, source="tool", conf=0.9))
    s.assert_node("dec_handoff", "decision",
        "During migration, NodeTransfer must renew the lease BEFORE copying node state; "
        "otherwise the stale owner keeps accepting writes and they are lost. This is the "
        "root cause of bug #43.", _p(ts=14, source="tool", conf=0.95))
    # irrelevant decision
    s.assert_node("dec_greedy", "decision",
        "Adopt greedy meshing for biome rendering to cut draw calls ~40%.",
        _p(agent="agent_Z", ts=15))

    # --- Relations (relevant cluster around task_B) ---------------------------
    s.assert_edge("task_B", "art_nodetransfer", "modifies", _p(ts=16))
    s.assert_edge("task_B", "dec_leases", "relates_to", _p(ts=17))
    s.assert_edge("task_B", "dec_handoff", "relates_to", _p(ts=18))
    s.assert_edge("task_B", "art_bug43", "relates_to", _p(ts=19))
    s.assert_edge("art_nodetransfer", "art_leasemanager", "depends_on", _p(ts=20))
    s.assert_edge("art_nodetransfer", "art_partitionmap", "depends_on", _p(ts=21))
    s.assert_edge("art_leasemanager", "ent_lease", "derived_from", _p(ts=22))
    s.assert_edge("art_partitionmap", "ent_partition", "derived_from", _p(ts=23))
    s.assert_edge("art_bug43", "dec_handoff", "relates_to", _p(ts=24))

    # A's original locking decision belonged to task_A, then got superseded:
    s.assert_edge("task_A", "dec_locking", "relates_to", _p(ts=25))
    s.supersede("dec_locking", "dec_leases", _p(ts=26, source="tool"))

    # irrelevant cluster (must NOT reach task_B)
    s.assert_edge("task_C", "art_biome", "modifies", _p(agent="agent_Z", ts=27))
    s.assert_edge("task_C", "dec_greedy", "relates_to", _p(agent="agent_Z", ts=28))
    s.assert_edge("art_biome", "ent_biome", "derived_from", _p(agent="agent_Z", ts=29))

    return s, "task_B"
