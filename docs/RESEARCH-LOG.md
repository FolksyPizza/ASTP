# MCTP Research Log

A running record of decisions, changes, and findings, kept for the eventual paper. Newest
entries are appended at the bottom. Each entry states what was decided or found and why.
Experimental numbers live in [EXPERIMENTS.md](EXPERIMENTS.md); this log records the reasoning.

Format: `### <date> — <title>` followed by Decision / Finding / Rationale.

---

### 2026-08 — Positioning: state layer, not summarizer
Decision: position MCTP as separating persistent agent state from active model context, not as
a compression or summarization system.
Rationale: the defensible contribution is structured, provenance-aware state transfer, not
smaller tokens. Operating principle: preserve everything, propagate selectively, retrieve
precisely.

### 2026-08 — Core vs Intelligence layering
Decision: split the system into a deterministic Core (protocol: state representation, storage,
audit log, provenance, retrieval, transfer) and an optional Intelligence Layer (learned
ranking, sufficiency prediction, adaptive feeding).
Rationale: the protocol must be reproducible, auditable, and model-independent; learned behavior
belongs in a layer on top so its contribution can be measured against a deterministic floor.

### 2026-08 — Deterministic selector as the baseline
Decision: the Core selector is a deterministic bounded graph walk (k-hop over the believed
subgraph from the task, excluding superseded/contradicted nodes and other tasks, budget-trimmed
by type). Retrieval is a content-addressed blob lookup.
Rationale: it is the reproducible floor and a strong baseline; a learned selector can only be
credited for the delta above it.

### 2026-08 — Artifact references over prose summaries
Finding: storing artifacts as prose summaries lost implementation detail the receiver needed
(the mctp agent had to ask for the actual code).
Decision: store artifacts as references (`path`, `content_hash`, `language`, `symbols`) with the
full source in a blob store, fetched on demand. This is hybrid delivery: high-value state inline,
artifacts as references, heavy content on demand.

### 2026-08 — Feedback/observation interface (episode record)
Decision: each handoff produces one `episode` record (context tokens, packet nodes, retrieved
ids/tokens, codebase reads, used nodes, outcome, misleading). Attention is not observable, so
"used" is inferred from behavior (references and pulls), not attention.
Rationale: this is both the evaluation unit and the training signal for the Intelligence Layer.

### 2026-08 — First benchmark findings (single trial, Claude, o200k_base)
Findings across ten hand-authored scenarios:
- Correctness held on nine of ten mctp cells; the tenth (`hidden_constraint`) failed.
- Token reduction is real but not universal and scales with how prunable the context is:
  large noisy investigations reduced ~67–72% total; a small already-concise transcript was
  token-worse (+50%).
- Receiver over-retrieval erodes the total-token advantage.
- Filtering a superseded decision can drop the *reason* it was rejected, which the transcript
  keeps.
Rationale: token reduction should not be the headline; correctness-at-cost and reliability are.

### 2026-08 — hidden_constraint: extraction fidelity is the ceiling
Finding: a required constraint present in the source was linked in the graph to the wrong task,
so the selector's packet omitted it and the receiver could not answer.
Conclusion: this is an extractor/linking failure, not a selector failure. A smarter selector
would not have fixed it because the node was not in the candidate set. Extraction and linking
fidelity bound the whole system. Turned into a negative-control scenario so the suite can fail
MCTP.

### 2026-08 — Real tokenizers
Decision: count tokens with real tokenizers (tiktoken encodings; optional Hugging Face) rather
than a chars/4 heuristic; report `o200k_base`.
Finding: the direction of every flat-vs-mctp comparison is the same under all tokenizers, so the
results are not an artifact of the estimate.

### 2026-08 — Model runner and scaling direction
Decision: add an OpenAI-compatible model runner (`--model`) so any local/hosted model can be the
receiver, and scale the benchmark via existing OSS suites rather than authoring more in-house
scenarios (the ten in-house scenarios stay as controls).

### 2026-08 — Semi-deterministic selection (adopted design)
Decision: for real usage the selector is semi-deterministic — a deterministic walk produces a
bounded, auditable candidate set, and a learned reranker/sufficiency-predictor (Intelligence
Layer) scores and prunes it. The learned model can only select from existing provenance-tagged
candidates, so it stays extractive and auditable, and its contribution is measurable against the
deterministic floor.
Rationale: reconciles adaptivity (needed in the real world) with reproducibility, auditability,
and portability of the protocol. The learned selector is trained on the benchmark's episode
labels (misses = recall, unused = precision).

### 2026-08 — Compute environment
Finding: the GPU server is a WSL VM; the GPU comes from the Windows host driver via `/dev/dxg`
(no Linux driver in the guest). Two RTX 3090s (48 GB) are live; Ollama already serves local
models (`qwen3.6:35b-128k`, `gemma3:27b`, `gpt-oss:20b`, phi models).
Decision: start local runs on Ollama's OpenAI-compatible endpoint; move heavy sweeps to vLLM in
an unprivileged venv for throughput. Install via venv (no sudo).

### 2026-08-21 — Local-model calibration (Ollama, gemma3:27b)
Finding: the runner drove gemma3:27b end to end through all ten scenarios (20 cells) via Ollama
in 2m16s (~6.8 s/cell). Warm single-stream throughput was ~39 generation tok/s and ~4,700
prefill tok/s on the two 3090s. Ollama serves single-stream (no batching) and reloads the model
on a switch. `qwen3.6:35b` is a reasoning model that returned empty content within a normal
token budget (its output went to thinking tokens); `gpt-oss:20b` returned HTTP 500.
Implications: (a) single-stream Ollama extrapolates to roughly days for a Phase-1 large-scale
sweep, so vLLM's continuous batching (target hours) is required for scale; (b) gemma3:27b scored
100% on the keyword checks, including a **false pass on the `hidden_constraint` negative
control** — confirming that keyword scoring over-credits and motivating judge-based scoring
before large runs.
Decision: install vLLM (unprivileged venv) for the sweeps, and upgrade scoring before scaling.
