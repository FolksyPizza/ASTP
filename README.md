# Model Context Transfer Protocol

MCTP is a protocol for reconstructing model-relevant state between AI models and agents.
Instead of transferring an entire conversation history, MCTP represents the important state
explicitly, transfers the high-value context, references deeper artifacts, and retrieves
their details only when they are needed.

MCTP is not primarily a compression system; it separates persistent agent state from active
model context. Its operating principle is *preserve everything, propagate selectively, retrieve
precisely*: the complete state (decisions, constraints, artifacts, provenance, and superseded
approaches) is stored and auditable, only the relevant current state is sent to the next agent,
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

- **Transcript** sends everything: "here is all of it, you figure it out."
- **Summary** sends an interpretation: "another model decided what you should know."
- **MCTP** preserves everything, sends the relevant current state, and keeps the underlying
  evidence retrievable on demand.

| | Transcript | Summary | MCTP |
|---|---|---|---|
| What the receiver gets | The full history | An LLM's condensed interpretation | Selected current-state nodes plus artifact references |
| Extra inference to prepare it | None | A summarization call (its cost must be counted) | None (deterministic selection) |
| Stale / superseded content | Included as-is | May keep or drop it, unpredictably | Excluded from the packet; retained in state and marked superseded |
| Provenance and exact source | Present but unstructured | Usually lost | Explicit and structured (source, agent, supersession) |
| Underlying information after handoff | Still in the transcript | Lost if the summary dropped it | Preserved and retrievable (`RETRIEVE <id>`) |
| Risk of omitting a critical fact | Low (it sends everything) | Real (the model may drop it) | Real only if the fact is not linked to the task (extraction fidelity is the ceiling) |
| Cost as history accumulates | Grows with the whole history | Re-summarize repeatedly | Active context stays small; state is stored separately |
| Structured / auditable | No | No | Yes |
| Built for agent-to-agent handoff | No | No | Yes |

The evaluation treats transcript, summary (counting the summarizer's inference), conventional
retrieval (RAG), and MCTP as separate baselines; see the
[benchmark design](https://github.com/FolksyPizza/MCTP-Bench/blob/main/docs/BENCHMARK.md).

## Architecture

MCTP is organized into three layers.

1. State layer: the explicit, high-value context that is always transferred, comprising goals,
   decisions (including rejected alternatives and supersession), constraints, and dependencies.
   Superseded or contradicted state is retained for audit but excluded from transfer by default.
2. Artifact layer: files, code, documents, and logs are represented as references
   (`path`, content hash, language, symbols, dependencies) rather than inlined summaries. The
   full source of truth is stored and fetched on demand.
3. Retrieval layer: deeper information is retrieved only when the receiver requests it
   (`RETRIEVE <id>`), so large or expensive content is not transferred pre-emptively.

Together these implement hybrid context delivery: always provide high-value state inline,
provide artifacts as references, and retrieve heavy content on demand.

The protocol is split into a Core layer (state representation, storage, audit log, retrieval,
provenance, transfer, usable with no trained models) and an optional Intelligence Layer
(learned ranking, sufficiency prediction, adaptive feeding). Only Core is the portable
protocol. See [docs/DESIGN.md](docs/DESIGN.md).

## Repository layout

```
core/mctp/     Core reference implementation (event-sourced store, selector, transfer)
docs/          PRIMER.md (start here), DESIGN.md (rationale), ARCHITECTURE.md (mechanics),
               ROADMAP.md, schema-v0.1.md, EXPERIMENTS.md, RESEARCH-LOG.md
bench/         local viability probe and handoff example
intelligence/  optional Intelligence Layer (design notes)
```

The evaluation harness lives in the companion repository
[MCTP-Bench](https://github.com/FolksyPizza/MCTP-Bench).

## Current results

These are interim results from a large-scale run: one capable model over the standard suites, at
a single trial per task. The model is a 27B-parameter open-weights model (Qwen3 series, 4-bit
quantized) served with a 128K context window, run under four conditions: `transcript` (the full
accumulated context), `summary` (same-model summarization), `rag` (TF-IDF retrieval), and `mctp`
(a believed-state packet selected to a token budget). Task success is an objective check:
executed unit tests for the code suites, exact-match answers otherwise. Each cell reports the
pass rate and the average delivered-context size in tokens (tiktoken `o200k_base`).

| Suite | transcript | summary | rag | mctp |
| --- | --- | --- | --- | --- |
| gsm8k | 97% / 0 | 97% / 0 | 97% / 0 | 97% / 63 |
| humaneval | 96% / 0 | 96% / 0 | 96% / 0 | 96% / 136 |
| mbpp | 82% / 0 | 82% / 0 | 82% / 0 | 81% / 52 |
| multifile | 100% / 80 | 91% / 279 | 100% / 75 | 100% / 157 |
| longbench | 51% / 12,360 | 40% / 836 | 37% / 354 | 50% / 180 |

Cells are pass rate / average context tokens.

On the low-context suites (gsm8k, humaneval, mbpp) the four conditions fall within a point of each
other. These tasks carry little prunable context, so the delivery method does not change the
outcome; MCTP does not cost accuracy where there is nothing to select.

The long-context suite is where the delivery method separates. On longbench, MCTP reaches the
accuracy of the full transcript (50% against 51%) while delivering about one sixty-ninth of the
context (180 tokens against 12,360), and it scores above both same-model summarization and TF-IDF
retrieval. That is the intended result: the accuracy of sending everything at a fraction of the
token cost.

The repobench, swebench, and multi-agent (swarm) suites are still being finalized and are not yet
reported. Full methodology and the per-suite tables are in the MCTP-Bench
[results doc](https://github.com/FolksyPizza/MCTP-Bench/blob/main/docs/RESULTS.md).

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

## Roadmap

Approximate targets for a research prototype, not commitments; dates may move as results come in.

- **Now (Aug 2026):** the Core reference implementation and the MCTP-Bench harness are complete.
  Nine evaluation suites (code, math, repository, long-context, and multi-agent) are prepared, and
  the large-scale runner (concurrent, checkpointed and resumable, roughly 300k receiver runs across
  a nine-model sweep) is validated end to end on local open models. The benchmark is ready to run.
- **Late Aug to Sep 2026:** throughput calibration, then the first full evaluation on the
  small-model wave (8 to 14B) across all suites, with deferred cross-review judge scoring, and the
  first public results.
- **Sep to Oct 2026:** the large-model wave (quantized 27 to 35B), SWE-bench native test-verified
  scoring, and a results leaderboard others can track.
- **Q4 2026:** Intelligence Layer v0.1, the learned selector and reranker, trained on the
  accumulated episodes (synthetic data; see [docs/MODEL-CARD.md](docs/MODEL-CARD.md)) and reported
  against the deterministic Core baseline.
- **Beyond:** adaptive context feeding, multi-agent swarm evaluation at scale, and schema v0.2.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the detailed phase plan.

## Status

Research prototype under active development. Interfaces and schema are versioned at v0.1 and
may change.
