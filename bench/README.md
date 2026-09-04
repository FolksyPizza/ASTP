# bench/, rough viability probe

```bash
python3 bench/viability_test.py
```

Builds a realistic handoff scenario (`scenario.py`), materializes the ASTP graph, runs the
Core baseline selector, and compares a structured ASTP packet against a naive flat dump.

**What it proves:** the Core pipeline works end-to-end (event log to graph to believed-state
 to selection to structured transfer to audit); the packet excludes stale (superseded) and
irrelevant state; the audit log is complete.

**What it does not prove:** that Agent B succeeds on the smaller packet, that needs a
model in the loop (ASTP-Bench, next). Token counts are a ~4 chars/token estimate. The flat
baseline is deliberately conservative (node contents only, no transcript filler), so the
reported reduction is a **floor**, not the realistic gap.
