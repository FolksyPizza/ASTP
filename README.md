# Model Context Transfer Protocol

MCTP is a protocol for reconstructing model-relevant state between AI models and agents.
Instead of transferring an entire conversation history, MCTP represents the important state
explicitly, transfers the high-value context, references deeper artifacts, and retrieves
their details only when they are needed.

MCTP is not primarily a compression system; it separates persistent agent state from active
model context. Its operating principle is *preserve everything, propagate selectively, retrieve
precisely*: the complete state — decisions, constraints, artifacts, provenance, and superseded
approaches — is stored and auditable, only the relevant current state is sent to the next agent,
and the original evidence stays retrievable on demand.

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

## Transcript vs. summary vs. MCTP

Three ways to hand work from one agent to the next:

- **Transcript** — sends everything: "here is all of it, you figure it out."
- **Summary** — sends an interpretation: "another model decided what you should know."
- **MCTP** — preserves everything, sends the relevant current state, and keeps the underlying
  evidence retrievable on demand.

| | Transcript | Summary | MCTP |
|---|---|---|---|
| What the receiver gets | The full history | An LLM's condensed interpretation | Selected current-state nodes + artifact references |
| Extra inference to prepare it | None | A summarization call (its cost must be counted) | None — deterministic selection |
| Stale / superseded content | Included as-is | May keep or drop it, unpredictably | Excluded from the packet; retained in state and marked superseded |
| Provenance & exact source | Present but unstructured | Usually lost | Explicit and structured (source, agent, supersession) |
| Underlying information after handoff | Still in the transcript | Lost if the summary dropped it | Preserved and retrievable (`RETRIEVE <id>`) |
| Risk of omitting a critical fact | Low — it sends everything | Real — the model may drop it | Real only if the fact is not linked to the task (extraction fidelity is the ceiling) |
| Cost as history accumulates | Grows with the whole history | Re-summarize repeatedly | Active context stays small; state is stored separately |
| Structured / auditable | No | No | Yes |
| Built for agent-to-agent handoff | No | No | Yes |

The evaluation treats transcript, summary (counting the summarizer's inference), conventional
retrieval (RAG), and MCTP as separate baselines; see the
[benchmark design](https://github.com/FolksyPizza/MCTP-Bench/blob/main/docs/BENCHMARK.md).

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
docs/           PRIMER.md (start here), DESIGN.md (rationale), ARCHITECTURE.md (mechanics),
                ROADMAP.md, schema-v0.1.md, EXPERIMENTS.md, RESEARCH-LOG.md
bench/          local viability probe and handoff example
intelligence/   optional Intelligence Layer (design notes)
```

The evaluation harness lives in the companion repository
[MCTP-Bench](https://github.com/FolksyPizza/MCTP-Bench).

## Current results

These results are preliminary and should be read as an existence check of the mechanism and
its costs, not as a general performance claim. The evaluation covers ten hand-authored
scenarios, a single trial per condition, all runs using Claude models, with task success judged
by keyword-based checks rather than human review. Each scenario is run under two conditions — a
`flat` baseline (the raw Agent-A transcript) and an `mctp` condition (the Core selector packet
with retrieve-on-demand) — by an isolated Claude subagent that sees only its context and an
identical neutral task. Reported totals include retrieval cost, not just the initial packet.
Token counts use the tiktoken `o200k_base` encoding; the direction of each comparison holds
under the other tokenizers tested.

Across the ten scenarios (20 conditions): the `flat` baseline passed all ten; the `mctp`
condition passed nine and failed one. On the nine where both pass, this compares context cost at
equal task success and does not demonstrate a correctness advantage for MCTP. The one failure is
instructive — in `hidden_constraint` a required constraint was present in the transcript but not
linked to the task in the graph, so the packet omitted it and the receiver could not answer;
extraction and linking fidelity, not the selector, is the ceiling.

On cost, MCTP reduced total tokens in eight of ten scenarios and increased them in two. The
effect scales with how much of the context is prunable:

| Scenario | flat total | mctp total | Δ total |
|----------|-----------:|-----------:|--------:|
| outage_investigation (large, noisy) | 2476 | 828 | −67% |
| payment_idempotency (large, noisy) | 2319 | 645 | −72% |
| bug43 (medium) | 783 | 513 | −35% |
| auth_migration (small, already concise) | 291 | 436 | +50% |

Below roughly 1,000 tokens there is often little to prune, so MCTP's structural overhead and any
retrieval can exceed the baseline; the benefit appears in larger, noisier contexts.

Full per-scenario descriptions are in the MCTP-Bench
[scenarios doc](https://github.com/FolksyPizza/MCTP-Bench/blob/main/docs/SCENARIOS.md), and full
methodology, per-run data, and interpretation are in [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

## Limitations

- A small number of hand-authored scenarios; results are not yet statistically meaningful.
- All model runs so far use Claude; there is no cross-model-family evidence yet. A local
  open-model sweep (vLLM, via the MCTP-Bench `--model` runner) is set up and is the next run.
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
