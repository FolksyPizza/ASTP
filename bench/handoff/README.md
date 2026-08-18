# bench/handoff — local two-agent handoff probe

A minimal, self-contained example of the bug43 handoff: two isolated "Agent B" instances
answer the same neutral question ("take over bug #43") from two different contexts.

- `baseline_transcript.txt` — the raw Agent-A session log (file dumps, benchmark output, and
  the abandoned distributed-locking approach).
- `mctp_packet.txt` — the MCTP structured packet from the Core selector, with artifacts as
  references and retrieve-on-demand.

Gold answer: (1) time-bounded leases; (2) renew the lease before copying node state;
(3) distributed locking was considered and rejected due to lock contention under load.

This directory is an illustrative example only. The canonical evaluation, including the full
scenario suite, scored episodes, and token counts under real tokenizers, lives in the
MCTP-Bench harness; see `../../MCTP-Bench` and `../docs/EXPERIMENTS.md`.
