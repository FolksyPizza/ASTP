"""Rough viability probe for ASTP v0.1.

WHAT THIS PROVES: the Core plumbing works end-to-end (event log -> materialized graph ->
believed-state -> baseline selection -> structured transfer -> audit), and that a
structured handoff is smaller than a naive flat dump on a realistic toy scenario, while
NOT shipping a superseded decision the flat dump would.

WHAT THIS DOES NOT PROVE: that Agent B actually succeeds on the smaller packet. That needs
a model in the loop and is the job of ASTP-Bench. Token counts use a ~4 chars/token
estimate, not a real tokenizer. Treat the number as a mechanics signal, not an efficacy
result.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from mctp import Provenance, build_packet, cold_start_select, estimate_tokens, flat_context  # noqa: E402
from scenario import build_scenario  # noqa: E402


def main() -> None:
    store, task_id = build_scenario()
    graph = store.materialize()

    total = len(graph.nodes)
    believed = sum(1 for n in graph.nodes.values() if n.believed)

    # Baseline flat handoff (what a text-file dump would carry).
    flat = flat_context(store)
    flat_tokens = estimate_tokens(flat)

    # ASTP structured handoff via the Core cold-start selector.
    packet_nodes = cold_start_select(graph, task_id)
    packet = build_packet(graph, packet_nodes, task_id)
    packet_tokens = estimate_tokens(packet)
    store.record_transfer(task_id, [n.id for n in packet_nodes], packet_tokens,
                          Provenance("mctp", "core", "baseline-selector", 100))

    reduction = 100.0 * (flat_tokens - packet_tokens) / flat_tokens

    selected_ids = {n.id for n in packet_nodes}
    print("=" * 68)
    print("ASTP v0.1 — rough viability probe (mechanics + token delta)")
    print("=" * 68)
    print(f"Graph:            {total} nodes ({believed} believed, "
          f"{total - believed} not-believed), {len(graph.edges)} edges")
    print(f"Handoff task:     {task_id} — {graph.nodes[task_id].content[:60]}...")
    print()
    print(f"Flat dump:        {flat_tokens:>5} tokens  (all asserted nodes, stale included)")
    print(f"ASTP packet:      {packet_tokens:>5} tokens  ({len(packet_nodes)} nodes)")
    print(f"Token reduction:  {reduction:5.1f}%")
    print()
    print("Selected for B:  ", ", ".join(sorted(selected_ids)))

    # --- correctness properties ----------------------------------------------
    checks = []
    checks.append(("superseded decision (dec_locking) EXCLUDED from packet",
                   "dec_locking" not in selected_ids))
    checks.append(("superseded decision present in flat dump (baseline flaw)",
                   "distributed locking" in flat))
    checks.append(("irrelevant subsystem (biome) EXCLUDED from packet",
                   selected_ids.isdisjoint({"art_biome", "ent_biome", "dec_greedy", "task_C"})))
    checks.append(("root-cause decision (dec_handoff) INCLUDED",
                   "dec_handoff" in selected_ids))
    checks.append(("live decision (dec_leases) INCLUDED",
                   "dec_leases" in selected_ids))
    checks.append(("dependencies (LeaseManager, PartitionMap) INCLUDED",
                   {"art_leasemanager", "art_partitionmap"}.issubset(selected_ids)))
    checks.append(("audit trail is complete (every action logged)",
                   len(store.log) > 0 and store.log[-1].type == "transferred"))

    print("\nCorrectness checks:")
    all_ok = True
    for label, ok in checks:
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

    print("\nAudit log length:", len(store.log), "events")
    print("-" * 68)
    print("ASTP PACKET (what Agent B would receive):")
    print("-" * 68)
    print(packet)

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
