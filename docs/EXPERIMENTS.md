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

1. Automated harness — `MCTP-Bench/run.py [--real]`. Uses the deterministic, model-free
   `MockRunner` to validate token accounting, retrieve-on-demand mechanics, episode logging,
   and scoring. The MockRunner echoes the delivered context, so its correctness score is not
   an efficacy measurement.
2. Model-in-the-loop — each condition is run by a fresh, isolated Claude subagent acting as
   "Agent B". The agent sees only its assigned context plus an identical neutral question,
   with no access to prior conversation. Retrieve-on-demand requests are fulfilled by
   returning the requested artifact. Results are logged via `record_run(...)` and tagged
   `runner=claude-subagent`.

The unit of data is the episode (PLAN.md §6.2): `{scenario, condition, runner,
context_tokens, packet_node_ids, retrieved_ids, retrieved_tokens, codebase_reads,
used_node_ids, outcome_pass, criteria, misleading}`, written to
`MCTP-Bench/results/episodes.jsonl`.

## Scenarios
- `bug43` (coding handoff) — partition-migration data loss. Correct fix: time-bounded leases;
  renew the lease before copying node state. Contains a superseded distributed-locking decision.
- `cache_staleness` (decision transfer) — distributed-cache stale reads. Correct fix:
  write-through invalidation with versioned keys; the read path compares version and reloads on
  mismatch. Contains a superseded TTL-tuning decision as a misdirection.
- `auth_migration` (decision transfer) — migration from server-side sessions to stateless JWT.
  Agent B must not regress to sessions. Contains a superseded session-store decision.
- `artifact_selection` (artifact retrieval) — a configuration value located in one file among
  several. Contains a look-alike distractor (a cache pool of 50 versus the DB pool of 20).

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

Total-token change (mctp relative to flat): bug43 −34.5%, cache_staleness −5.0%,
artifact_selection −25.5%, auth_migration +49.8%. Upfront-context change: bug43 −46.4%,
cache_staleness −25.1%, artifact_selection −44.0%, auth_migration +17.2%. The direction of
each comparison is unchanged under the other tokenizers (see
`MCTP-Bench/results/token_comparison.md`).

MockRunner rows in `episodes.jsonl` reproduce the same token and pull structure, confirming
the harness independently of any model.

## Findings
1. Equal task success. In all eight cells every isolated Agent B passed the heuristic checks
   with zero misleading answers, including both `flat` baselines. Because the baseline also
   passed, this study compares context cost at equal task success; it does not demonstrate a
   correctness or reliability advantage for MCTP. Task success is judged by keyword-based
   checks, not human review.
2. Token reduction is real but not universal. MCTP reduced total tokens in three of four
   scenarios (5–35%) and upfront context in three of four (25–46%). In `auth_migration` it was
   token-worse (+49.8% total, +17.2% upfront) because the flat transcript was already concise
   and the mctp agent made two pulls. Token reduction should not be treated as the headline.
3. Receiver over-retrieval erodes the total-token advantage. In `cache_staleness` and
   `auth_migration` the mctp agent produced a correct answer from references before retrieving,
   then made confirmatory pulls that were not strictly necessary. This is a receiver-side
   precision problem and motivates the Intelligence Layer (sufficiency prediction, suppression
   of unneeded retrieve affordances).
4. Filtering a superseded decision can remove useful rejected-alternative context. In
   `auth_migration` the flat agent cited the rejected "scale the store" sub-option, while the
   mctp agent could not, because the selector excluded the superseded session decision
   entirely. This suggests superseded decisions may need to be delivered tagged as rejected
   rather than omitted, so the receiver knows what not to revisit (relevant to PLAN.md §4.6).
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
   vague request for source into a precise, targeted retrieval (PLAN.md §8.6.1, §8.6.2).

## Data and artifact index
- Episodes: `MCTP-Bench/results/episodes.jsonl`
- Verbatim agent outputs: `MCTP-Bench/results/transcripts/`
- Harness and summary table: `MCTP-Bench/run.py`, `MCTP-Bench/README.md`
- Scenarios: `MCTP-Bench/scenarios/{bug43,cache_staleness}.py`
- Core implementation: `MCTP/core/mctp/{model,store,retrieval,transfer}.py`
- Raw handoff contexts (bug43): `MCTP/bench/handoff/`
- Design and interpretation: `MCTP/PLAN.md` §3.5, §4.2, §6.2, §8.5–8.7

## Limitations
- Single trial per condition; no variance is reported.
- All model runs use Claude; there is no cross-model-family evidence yet.
- `check()` is a keyword heuristic, not a semantic grader.
- Scenarios are small and hand-authored; the MCTP graphs are authored rather than produced by
  an extractor, so extraction fidelity is not yet measured (PLAN.md open question #8).
- Token counts use tiktoken (OpenAI encodings) and the chars/4 heuristic. Open-model
  tokenizers (Qwen, Llama, and similar) are supported by the harness but were not available in
  this environment, so cross-family tokenization is not yet reported.

## Reproduction
```
MCTP_HOME=../MCTP python3 MCTP-Bench/run.py --real
```
