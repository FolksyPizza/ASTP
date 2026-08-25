# MCTP Experiments

Record of MCTP evaluation experiments: methodology, results, data locations, and
limitations.

## Environment
- Language: Python 3, standard library only. No network or API keys required for the harness.
- Repositories: `MCTP` (protocol and Core reference implementation) and `MCTP-Bench`
 (evaluation harness), located as sibling directories.
- Token counts use real tokenizers via `mctpbench/tokenizers.py`. Reported figures use
 tiktoken `o200k_base` (GPT-4o-class). A cross-tokenizer comparison (heuristic, gpt2,
 cl100k_base, o200k_base) is in `MCTP-Bench/results/token_comparison.md`; the direction of
 every flat-versus-mctp comparison is the same under all four. tiktoken is installed in the
 MCTP-Bench virtualenv, so real-tokenizer runs use `.venv/bin/python`.

## Method
Two execution paths are used, kept separate:

1. Automated harness: `MCTP-Bench/run.py [--real]`. Uses the deterministic, model-free
 `MockRunner` to validate token accounting, retrieve-on-demand mechanics, episode logging,
 and scoring. The MockRunner echoes the delivered context, so its correctness score is not
 an efficacy measurement.
2. Model-in-the-loop: each condition is run by a fresh, isolated Claude subagent acting as
 "Agent B". The agent sees only its assigned context plus an identical neutral question,
 with no access to prior conversation. Retrieve-on-demand requests are fulfilled by
 returning the requested artifact. Results are logged via `record_run(...)` and tagged
 `runner=claude-subagent`.

The unit of data is the episode (see [DESIGN.md](DESIGN.md)): `{scenario, condition, runner,
context_tokens, packet_node_ids, retrieved_ids, retrieved_tokens, codebase_reads,
used_node_ids, outcome_pass, criteria, misleading}`, written to
`MCTP-Bench/results/episodes.jsonl`.

## Scenarios
- `bug43` (coding handoff), partition-migration data loss. Correct fix: time-bounded leases;
 renew the lease before copying node state. Contains a superseded distributed-locking decision.
- `cache_staleness` (decision transfer), distributed-cache stale reads. Correct fix:
 write-through invalidation with versioned keys; the read path compares version and reloads on
 mismatch. Contains a superseded TTL-tuning decision as a misdirection.
- `auth_migration` (decision transfer), migration from server-side sessions to stateless JWT.
 Agent B must not regress to sessions. Contains a superseded session-store decision.
- `artifact_selection` (artifact retrieval), a configuration value located in one file among
 several. Contains a look-alike distractor (a cache pool of 50 versus the DB pool of 20).
- `payment_idempotency` (larger repository task), a duplicate-charge investigation with a
 ~2,300-token flat transcript. Correct fix: deduplicate by idempotency key before charging.
 Contains two superseded approaches (a per-user lock and a timestamp heuristic) and several
 files that are read but irrelevant.
- `schema_migration` (larger task, hard constraints), a zero-downtime column migration.
 Correct fix: expand/contract; never a blocking ALTER or a maintenance window.
- `api_versioning` (decision transfer), v2 API auth. Correct fix: Bearer token in the
 Authorization header; do not reintroduce the deprecated URL query-string token.
- `flaky_test` (coding handoff), a time-dependent flaky test. Correct fix: inject a Clock and
 control time; not a retry or sleep band-aid.
- `hidden_constraint` (negative control), a bulk-delete endpoint whose GDPR soft-delete
 constraint is present in the transcript but not linked to the task in the graph.
- `outage_investigation` (larger task), a ~2,500-token cascading-outage RCA. Correct fix:
 single-flight coalescing on the cache read path plus a rate-based circuit breaker; not scaling
 out or raising timeouts. Full descriptions of all scenarios are in the MCTP-Bench repository's
 `docs/SCENARIOS.md`.

## Results (runner = claude-subagent, n = 1 per condition, tokenizer = tiktoken o200k_base)

| Scenario | Condition | Pass | Context tok | Retrieved tok | Total tok | Pulls | Misleading |
|----------|-----------|------|-------------|---------------|-----------|-------|------------|
| bug43 | flat | pass | 783 | 0 | 783 | 0 | 0 |
| bug43 | mctp | pass | 420 | 93 | 513 | 1 | 0 |
| cache_staleness | flat | pass | 557 | 0 | 557 | 0 | 0 |
| cache_staleness | mctp | pass | 417 | 112 | 529 | 2 | 0 |
| auth_migration | flat | pass | 291 | 0 | 291 | 0 | 0 |
| auth_migration | mctp | pass | 341 | 95 | 436 | 2 | 0 |
| artifact_selection | flat | pass | 184 | 0 | 184 | 0 | 0 |
| artifact_selection | mctp | pass | 103 | 34 | 137 | 1 | 0 |
| payment_idempotency | flat | pass | 2319 | 0 | 2319 | 0 | 0 |
| payment_idempotency | mctp | pass | 486 | 159 | 645 | 2 | 0 |
| schema_migration | flat | pass | 717 | 0 | 717 | 0 | 0 |
| schema_migration | mctp | pass | 379 | 227 | 606 | 3 | 0 |
| api_versioning | flat | pass | 299 | 0 | 299 | 0 | 0 |
| api_versioning | mctp | pass | 278 | 0 | 278 | 0 | 0 |
| flaky_test | flat | pass | 386 | 0 | 386 | 0 | 0 |
| flaky_test | mctp | pass | 287 | 114 | 401 | 3 | 0 |
| hidden_constraint | flat | pass | 300 | 0 | 300 | 0 | 0 |
| hidden_constraint | mctp | **fail** | 190 | 0 | 190 | 0 | 0 |
| outage_investigation | flat | pass | 2476 | 0 | 2476 | 0 | 0 |
| outage_investigation | mctp | pass | 503 | 325 | 828 | 4 | 0 |

Every `flat` condition passed; every `mctp` condition passed except `hidden_constraint`, where
the packet omitted a critical constraint (finding 8). Total-token change (mctp relative to
flat): bug43 -34.5%, cache_staleness -5.0%, artifact_selection -25.5%, auth_migration +49.8%,
payment_idempotency -72.2%, schema_migration -15.5%, api_versioning -7.0%, flaky_test +3.9%,
hidden_constraint -36.7%, outage_investigation -66.6%. The direction of each comparison is
unchanged under the other tokenizers (see `MCTP-Bench/results/token_comparison.md`).

MockRunner rows in `episodes.jsonl` reproduce the same token and pull structure, confirming
the harness independently of any model.

## Findings
1. Task success. The `flat` baseline passed all ten scenarios; the `mctp` condition passed nine
 and failed one (`hidden_constraint`, finding 8). On the nine scenarios where both conditions
 pass, the study compares context cost at equal task success and does not demonstrate a
 correctness advantage for MCTP; the tenth is a case where MCTP loses. There were zero
 misleading answers. Task success is judged by keyword-based checks, not human review.
2. Token reduction is real but not universal: and it scales with the amount of prunable
 context. MCTP reduced total tokens in eight of ten scenarios and was token-worse in two.
 The effect tracks how much of the flat context is prunable (irrelevant files, dead-ends,
 stale decisions): the large, noisy investigations `outage_investigation` (~2,500 tokens) and
 `payment_idempotency` (~2,300 tokens) saw -66.6% and -72.2% total; the already-concise
 `auth_migration` (~290 tokens) saw +49.8%, where the packet's structural overhead plus two
 pulls exceeded the baseline, and `flaky_test` (~390 tokens) saw +3.9%. Below roughly 1,000
 tokens there is often little to prune, so MCTP's overhead can dominate; the benefit appears
 in larger, noisier contexts. Token reduction should not be treated as the headline.
3. Receiver over-retrieval erodes the total-token advantage. In `cache_staleness` and
 `auth_migration` the mctp agent produced a correct answer from references before retrieving,
 then made confirmatory pulls that were not strictly necessary. This is a receiver-side
 precision problem and motivates the Intelligence Layer (sufficiency prediction, suppression
 of unneeded retrieve affordances).
4. Filtering a superseded decision can remove useful rejected-alternative context. In
 `auth_migration` the flat agent cited the rejected "scale the store" sub-option, while the
 mctp agent could not, because the selector excluded the superseded session decision
 entirely. This suggests superseded decisions may need to be delivered tagged as rejected
 rather than omitted, so the receiver knows what not to revisit (relevant to the
 retraction-versus-maintenance design in [DESIGN.md](DESIGN.md)). The same pattern recurred in
 `payment_idempotency`: the mctp agent knew the lock and heuristic approaches were superseded
 but could not state why they specifically failed, while the flat agent could.
5. Selective transfer avoids distractor content. In `artifact_selection` the mctp condition
 delivered only the relevant reference; the agent made one targeted retrieve and was never
 exposed to the look-alike cache pool value. The flat agent had all files inline and answered
 correctly here, but the failure surface (reporting the wrong pool) existed only in the flat
 condition.
6. No misleading answers. No superseded decision produced an incorrect solution: MCTP filtered
 them via the `supersedes` edge, and the flat transcripts stated them as rejected. A weaker
 model, or a transcript omitting the rejection, could still be misled; untested.
7. Artifact references resolve the earlier representation gap. Replacing prose-summary
 artifacts with references (`{path, hash, symbols}`) plus retrieve-on-demand converted a
 vague request for source into a precise, targeted retrieval.
8. MCTP loses when extraction is incomplete. In `hidden_constraint` a critical constraint (all
 deletions must use the soft-delete path) was present in the flat transcript but linked in the
 graph to the compliance task rather than the bulk-delete task, so the selector's packet
 omitted it. The flat agent answered correctly; the mctp agent recognized the deletion method
 was unspecified and abstained. This confirms that extraction and linking fidelity, not the
 selector, is the system's ceiling: state that is captured but not connected to the task is
 invisible to transfer. It also exposes a scoring limitation, a keyword check can be fooled
 by the mere presence of the `softDelete` symbol in the packet, so this cell is judged on
 whether the receiver committed to the compliant path, which it did not.

## Data and artifact index
- Episodes: `MCTP-Bench/results/episodes.jsonl`
- Verbatim agent outputs: `MCTP-Bench/results/transcripts/`
- Harness and summary table: `MCTP-Bench/run.py`, `MCTP-Bench/README.md`
- Scenarios: `MCTP-Bench/scenarios/{bug43,cache_staleness}.py`
- Core implementation: `MCTP/core/mctp/{model,store,retrieval,transfer}.py`
- Raw handoff contexts (bug43): `MCTP/bench/handoff/`
- Design and interpretation: [docs/DESIGN.md](DESIGN.md)

## Limitations
- Single trial per condition; no variance is reported.
- All model runs use Claude; there is no cross-model-family evidence yet.
- `check()` is a keyword heuristic, not a semantic grader.
- Scenarios are small and hand-authored; the MCTP graphs are authored rather than produced by
 an extractor, so extraction fidelity is not yet measured (an open research question; see
 [DESIGN.md](DESIGN.md)).
- Token counts use tiktoken (OpenAI encodings) and the chars/4 heuristic. Open-model
 tokenizers (Qwen, Llama, and similar) are supported by the harness but were not available in
 this environment, so cross-family tokenization is not yet reported.

## Reproduction
```
MCTP_HOME=../MCTP python3 MCTP-Bench/run.py --real
```
