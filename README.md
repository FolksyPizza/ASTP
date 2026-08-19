# Model Context Transfer Protocol (MCTP)

MCTP is a protocol for reconstructing model-relevant state between AI models and agents.
Instead of transferring an entire conversation history, MCTP represents the important state
explicitly, transfers the high-value context, references deeper artifacts, and retrieves
their details only when they are needed.

MCTP is not primarily a compression system. Its objective is to preserve task correctness
while reducing the amount of context that must be transferred, by moving structured state
rather than raw transcripts.

## Overview

Agent-to-agent and model-to-model workflows commonly hand off work as raw transcripts or as
free-text summaries. Both are lossy in ways that matter: transcripts carry stale content
(abandoned approaches, superseded decisions) and large volumes of low-value text, while
summaries can omit implementation detail the receiver needs. MCTP addresses this by
transferring an explicit, provenance-tracked representation of state, with source material
available on demand.

Scope is deliberately limited. MCTP does not attempt to solve AI memory in general, does not
replace retrieval, and does not guarantee optimal context selection. See
[docs/DESIGN.md](docs/DESIGN.md) for the full list of non-goals.

## Architecture

MCTP is organized into three layers.

1. State layer — the explicit, high-value context that is always transferred: goals,
   decisions (including rejected alternatives and supersession), constraints, and
   dependencies. Superseded or contradicted state is retained for audit but excluded from
   transfer by default.
2. Artifact layer — files, code, documents, and logs are represented as references
   (`path`, content hash, language, symbols, dependencies) rather than inlined summaries. The
   full source of truth is stored and fetched on demand.
3. Retrieval layer — deeper information is retrieved only when the receiver requests it
   (`RETRIEVE <id>`), so large or expensive content is not transferred pre-emptively.

Together these implement hybrid context delivery: always provide high-value state inline,
provide artifacts as references, and retrieve heavy content on demand.

The protocol is split into a Core layer (state representation, storage, audit log, retrieval,
provenance, transfer — usable with no trained models) and an optional Intelligence Layer
(learned ranking, sufficiency prediction, adaptive feeding). Only Core is the portable
protocol. See [docs/DESIGN.md](docs/DESIGN.md).

## Repository layout

```
core/mctp/      Core reference implementation (event-sourced store, selector, transfer)
docs/           design (DESIGN.md), schema (schema-v0.1.md), experiments (EXPERIMENTS.md)
bench/          local viability probe and handoff example
intelligence/   optional Intelligence Layer (design notes)
```

The evaluation harness lives in the companion repository
[MCTP-Bench](https://github.com/FolksyPizza/MCTP-Bench).

## Current results

These results are preliminary and should be read as an existence check of the mechanism and
its costs, not as a general performance claim. The evaluation covers four hand-authored
scenarios, a single trial per condition, all runs using Claude models, with task success
judged by keyword-based checks rather than human review. Token counts use the tiktoken
`o200k_base` encoding; the direction of each comparison is the same under the other tokenizers
tested (see the [token comparison](https://github.com/FolksyPizza/MCTP-Bench/blob/main/results/token_comparison.md)
in MCTP-Bench).

Each scenario is run under two conditions — a `flat` baseline (the raw Agent-A transcript) and
an `mctp` condition (the Core selector packet with retrieve-on-demand) — by an isolated Claude
subagent that sees only its context and an identical neutral task. Reported totals include
retrieval cost, not just the initial packet.

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

Every condition passed the checks with no misleading answers, including both `flat` baselines.
Because the baseline also passed, these scenarios compare context cost at equal task success;
they do not demonstrate a correctness or reliability advantage for MCTP, and larger or more
adversarial scenarios would be needed to test for one. On cost, the `mctp` condition reduced
total tokens in four of five scenarios and increased them in one. The effect scales with how
much of the context is prunable: the ~2,300-token `payment_idempotency` investigation saw a
−72% total reduction, while the already-concise ~290-token `auth_migration` transcript saw
about +50%, where the packet's structure and two pulls exceeded the small baseline. Below
roughly 1,000 tokens there is often little to prune.

Full methodology, per-run data, and interpretation are in
[docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

## Limitations

- A small number of hand-authored scenarios; results are not yet statistically meaningful.
- All model runs use Claude; there is no cross-model-family evidence.
- Human validation of scoring has not been performed; correctness is judged by keyword-based
  checks.
- Token counts use tiktoken (OpenAI encodings); open-model tokenizers (Qwen, Llama, and
  similar) are supported by the harness but were not exercised in this environment.
- The benchmark is early; scenario coverage and scoring are still maturing.
- MCTP graphs in the scenarios are authored, not produced by an extractor, so extraction
  fidelity is not yet measured.

## Status

Research prototype under active development. Interfaces and schema are versioned at v0.1 and
may change.
