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

### 2026-08-21 — Reasoning models are in scope; runner handling
Decision: reasoning ("thinking") models are a first-class part of the benchmark, not excluded —
they are a major and growing class of agents.
Finding: via Ollama, `qwen3.6` returns the final answer in the OpenAI `content` field and the
chain-of-thought in a separate `reasoning` field. A too-small `max_tokens` is consumed by
thinking and the answer is never emitted (empty content). Reasoning also multiplies output
tokens (~1,100+ for a trivial question; thousands for a handoff), which raises time and cost
roughly 3–10× over a non-reasoning model of similar size.
Changes: the runner now extracts the answer robustly (strip `<think>...</think>`, fall back to
the `reasoning` field), and exposes `--max-tokens` / `MCTP_MAX_TOKENS` (default 2048; use 4096+
for heavy reasoners). Open item: record output/thinking tokens per episode so total-cost metrics
count reasoning cost — reasoning models are exactly where structured state may change the
cost/benefit, so this must be measured, not assumed.

### 2026-08-23 — Model unloading, wave script, and a cross-category smoke test
Built (MCTP-Bench):
- Model lifecycle / unload-when-idle: `--window` now takes `--on-pause` / `--on-resume` shell
  hooks (WindowGate runs them when the window closes/opens), and `scripts/serve_vllm.sh` /
  `stop_vllm.sh` start/stop a vLLM server to free the GPU. `scripts/run_wave.sh` runs a wave that
  starts vLLM per model, runs the suites, and stops it before the next model — only the model in
  use holds the GPU. (Ollama unloads on its own keep-alive; vLLM is server-lifetime, hence this.)
- `scripts/smoke.sh ... all`: a cross-category smoke test — one task from every suite (all
  conditions), exercising each adapter, the extractor, and the swarm pipeline. Verified offline:
  all nine categories run one task each with zero errors.
Rationale: each vLLM process serves one model for its lifetime, so unloading is a process-lifecycle
concern the harness now manages rather than assuming models stay resident.

### 2026-08-23 — Per-model endpoints, telemetry socket + monitor, smoke run
Clarification: the runner varies context (the four conditions build different contexts from one
Source) and iterates models, but each vLLM process serves one model — so model switching is a
server concern, not something the runner "loads".
Built (MCTP-Bench):
- Per-model endpoints: `--models` accepts `model@url`, so a sweep can fan out across several vLLM
  servers (e.g. a small model per GPU) instead of assuming one endpoint serves all models.
- Live telemetry (`mctpbench/telemetry.py`): the runner serves a status snapshot on a localhost
  socket; `monitor.py` connects and renders a dashboard (progress bar, rate, ETA, pass/fail/error
  tallies, current run), watchable over an SSH tunnel. Best-effort — a bind failure or a dropped
  monitor never affects the sweep. Verified offline via a server↔client round-trip.
- `scripts/smoke.sh`: a fast first run (one small model, low-context suites, a few tasks each,
  transcript+mctp) to validate the end-to-end path before a full wave.
No model server contacted.

### 2026-08-23 — Graceful pause/stop
Built: `StopController` (in `mctpbench/orchestrate.py`) for a clean pause — Ctrl-C/SIGTERM, or a
`results/progress/<suite>.stop` file created from another terminal, requests a stop that finishes
the current run, saves, and stops (a second Ctrl-C aborts). The stop-file is cleared once honored
so `--resume` continues. Verified offline: stop-file honored, cleared, and resume completes.

### 2026-08-23 — Sweep orchestration, open-model tokenizers, and repo-suite data prep
Built (MCTP-Bench):
- Orchestration (`mctpbench/orchestrate.py` + `run_benchmark` flags): checkpoint/resume via an
  append-only manifest (interrupt/crash/`--max-hours` loses at most the in-flight run; `--resume`
  continues), a `--window HH:MM-HH:MM` clock gate (wraps midnight, e.g. off-hours only), a
  `--max-hours` budget, and progress with a rolling rate and ETA. Verified offline.
- Open-model tokenizers as reference counts: `tokenizers.reference_set()` now adds HF tokenizers
  (Qwen, Llama by default; `MCTP_HF_TOKENIZERS` / `MCTP_REF_TOKENIZERS` configurable) to the
  tiktoken encodings, so amounts are comparable across the families actually run, not only OpenAI's.
- Repo-suite data prep: `prepare_datasets.py` now materializes SWE-bench `files` per instance by
  checking out repo@base_commit and reading the patch-touched files, and maps RepoBench to our
  schema; both wired into `fetch_datasets.sh`. The patch file-path parser is verified offline.
No model server contacted.

### 2026-08-23 — Full matrix code-ready; dataset preparation scripted
Built: the medium multi-file adapter (`multifile`), the last unbuilt suite — small project
snapshots with a bug/reasoning task, scored by line- or substring-match, mctp state via the
extractor. Every planned suite now has an adapter, so all ~157k receiver runs are code-ready
(the plan's ready count equals the full-program total). Also added `scripts/prepare_datasets.py`
(converts MBPP, GSM8K, LongBench, and SWE-bench metadata into the adapter JSONL schemas via the
datasets library) and wired it into `fetch_datasets.sh`; `setup_host.sh` now installs `datasets`.
Open data-prep (not code): SWE-bench `files` snapshots require a checkout of repo@base_commit
per instance, and RepoBench needs a dataset-specific assembler — until those, those two suites
run only on bundled samples. No model server contacted.

### 2026-08-22 — All suites wired: high-context adapters and the multi-handoff tier
Decision: judging topology is swappable at will — scoring is a post-hoc pass over stored outputs
and never modifies model data — so the panel/cross-review split can change later without re-running.
Built (MCTP-Bench): the remaining adapters, so every planned suite is wired. `swebench`
(issue→patch, repo materialized to MCTP state via the extractor; objective scoring deferred to the
SWE-bench harness), `repobench` (cross-file next-line completion, line-match scorer), and
`longbench` (long-document QA, any-answer match or judge). The subagent/swarm tier is implemented
as a multi-handoff pipeline (`mctpbench/pipeline.py` + the `swarm` adapter): stages share evolving
state, each recorded as its own run. Also fixed a real gap — the matrix runner now passes each
adapter's receiver instruction to the model (previously every suite got the handoff prompt), so
code suites are asked to complete code rather than to write a handoff.
Finding (offline, MockRunner): all eight suites build and record; the swarm pipeline shows the
intended signal — per-stage context under `transcript` grew 43→91→187 tokens (re-sending the
whole history) while under `mctp` it stayed 32→62→93 (a selected packet). With a streaming mock, a
real code answer passes the HumanEval unit tests through the objective scorer. ~135.5k of the
~157k receiver runs are now runnable without further code (only a curated medium multi-file set is
left unbuilt). No model server contacted.

### 2026-08-22 — Judge topology, low-context adapters, and the extractor
Decision (judge topology): the independent panel is the PRIMARY, reported label — each of ≥3
mixed-family judges is reduced to one verdict (median score, majority pass) and the panel
aggregates by majority/median; this is the metric validated against a human sample. Cross-review
is kept as a SECONDARY signal (does peer critique flip the panel, and how far do scores shift),
because showing judges each other's verdicts introduces anchoring. Cross-review is optional.
Built (MCTP-Bench): MBPP and GSM8K adapters with objective scorers (unit tests / final-number
match), completing the low-context suite; and the extractor (`extraction/`) — a deterministic
`HeuristicExtractor` (files→artifact nodes with parsed symbols + import-derived `depends_on`
edges, task linked to named files) and an `LLMExtractor` skeleton (a model emits the closed v0.1
node/edge vocabulary including superseded decisions, validated on build). Verified offline: the
heuristic extractor's packet includes a task's dependencies and excludes an unrelated file, and
the LLM builder drops off-vocabulary types/edges and applies supersession.
Finding: with the low-context adapters built, ~42.6k receiver runs are now runnable without the
extractor (all of Phase 0 plus the in-house controls); the extractor gates the Phase-2 high-context
suites. Still no model server contacted.

### 2026-08-22 — Deferred cross-review scoring, run plan, and reasoning-on-all
Decision: store all receiver data first and score entirely afterward, with a richer judge than a
single-vote ensemble. The deferred pass (`scoring/judge.py`) runs three stages — independent
scoring (≥3 mixed-family judges, 2 samples each at nonzero temperature), cross-review (each judge
critiques the others' verdicts and revises), and aggregation (majority pass + median score, with
inter-judge disagreement, sample instability, and the round-1→round-2 shift recorded). Every judge
input/output is stored so the scoring is auditable and re-aggregatable.
Decision: reasoning models are run on all scenarios (a reasoning model is included in every wave),
not a subset, since reasoning agents are exactly where structured state may change the cost/benefit.
Decision: run the whole program in two waves — first all suites on small models (8–14B), then again
on large models (27–35B). The small wave is a result in itself and de-risks the pipeline at scale.
Finding: the plan (`bench_plan.py`) totals ~157k receiver runs across the full program (~6.6k
runnable now with the built adapters), plus deferred judging of ~0.5M calls over open-ended outputs
(objective suites are scored programmatically and judged only as a validation sample). All of this
is code and configuration; no model server has been contacted and no run performed.

### 2026-08-22 — Large-scale benchmark framework built (no runs yet)
Decision: implement the full data-capture framework before the first recorded run, so every run
preserves raw and parsed data additively.
Built (MCTP-Bench): a streaming runner (`mctpbench/streaming.py`) that captures the verbatim
request(s), every streamed chunk with its wall-clock offset, the server `usage` (native token
counts), and assembled answer/reasoning; a run-record schema and storage tree
(`mctpbench/records.py`, writing `runs/ raw/ outputs/ judge/ aggregates/ configs/`); the four
condition builders (`conditions/`: transcript, same-model summary, dependency-free TF-IDF rag,
Core mctp packet); suite adapters (`adapters/`: `humaneval` with an objective unit-test scorer,
`inhouse` wrapping the ten controls); objective scorers and an ensemble judge pass (`scoring/`);
the matrix runner (`run_benchmark.py`) with a `--dry-run` mode; pricing/aggregation (`analyze.py`);
and host-setup scripts.
Finding: validated end to end offline with the deterministic MockRunner and a mocked SSE stream —
all four conditions build, the storage tree writes, native + reference token counts and the raw
capture are recorded, the HumanEval scorer passes the canonical solution and fails a wrong one, and
`analyze.py` produces priced aggregates. No model server was contacted; no benchmark has been run.
Note: for stateless suites (HumanEval) the conditions coincide, so Phase-0 is a pipeline/scoring
validation, not a transfer comparison; the transfer comparison lives in the in-house controls and
the high-context suites that await the extractor.

### 2026-08-21 — vLLM vs Ollama throughput (expectation)
Note: Ollama serves single-stream, so its aggregate throughput equals its per-request rate
(~39 gen tok/s for gemma3:27b here). vLLM's per-request speed is comparable, but its continuous
batching runs many requests at once, so aggregate throughput for a sweep is far higher
(order 10–30× at short context, less at long context where KV cache limits the batch). Per
request ≈ same; whole-sweep ≈ much faster — the reason vLLM is required for scale. To be
confirmed by measuring a batched vLLM run.
