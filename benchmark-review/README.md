# MCTP-Bench review

A local, full-audit viewer for the benchmark results, with grading and flagging. Everything here
runs on this machine with no cloud dependency and no packages to install.

## Layout

```
benchmark-review/
  review_app.py          the app (Python standard library only)
  README.md              this file
  data/results/          the full results store (5.7 GB, git-ignored)
    runs/                per-suite/model/condition run records (the index source)
    raw/                 full request/response capture, one file per run
    outputs/             prompt, output, reasoning, and per-token timeline per run
    aggregates/          committed summary tables
    review.db            grades and flags you add (created on first run)
```

The same data is archived in the OCI bucket as `mctp-results-2026-09-02.tar.gz` (see
`../oci-bucket-access/`), so this local copy can be rebuilt at any time.

## Run it

```bash
cd benchmark-review
python3 review_app.py --results ./data/results
```

Then open <http://localhost:8080>. Options: `--port <n>` to change the port, `--rebuild` to
re-index after new data is added. First launch builds a SQLite index of all runs (a few seconds);
later launches reuse it.

## What it does

- **Browse and filter** every run by suite, model, **compute instance** (`3060 · vLLM` vs
  `3090 · Ollama`), condition, pass/fail/none, and review state (graded, ungraded, flagged).
  Free-text search over task and run id.
- **Sort** by any column, including latency, output tokens, context tokens, and decode tokens/sec.
- **Resize** the split: drag the divider to widen the detail pane and read completions in full
  (the width is remembered).
- **Inspect one run** in full: every recorded field (each on its own line, no overlap) plus the
  complete audit — the exact prompt, the output, any reasoning, the per-token timeline (token
  speeds), and the raw request/response.
- **MCTP packet audit**: for `mctp` and `mctp-r` runs, the metadata shows `packet_node_ids` (the
  believed-state nodes the selector chose), `retrieved_ids` and `retrieved_tokens` (what was
  pulled on demand), and `prep_tokens`. The Prompt tab shows the delivered packet itself.
- **Subagent pipelines**: open any `swarm` run and the detail pane shows the whole pipeline in
  order — every stage's role, its objective verdict, its context size, and its output — so you can
  follow the handoffs and check whether the carried decision survived to the final stage.
- **Grade** (correct / partial / incorrect / unsure) and **flag** (scorer-wrong / interesting /
  bug / revisit) with a note. Grades and flags **autosave** to `data/results/review.db` and never
  modify the run records. Keyboard: `j`/`k` move, `1`–`4` grade, `f` flag revisit, `n` jump to the
  next ungraded run.
- **Overall statistics** (header button): per suite/model/condition pass rates, none counts, and
  mean context/output tokens and latency.
- **Export** reviews as CSV; **light and dark** themes.

## The data

Each run record carries 38 fields. The ones worth knowing:

| Field | Meaning |
| --- | --- |
| `suite`, `model`, `condition`, `trial` | what was run |
| `objective_pass`, `objective_detail` | scorer verdict and its evidence (e.g. gold vs predicted) |
| `started_at`, `ttft_s`, `latency_s` | timestamp, time-to-first-token, end-to-end latency |
| `prompt_tokens`, `output_tokens`, `reasoning_tokens` | token accounting |
| `context_tokens`, `context_tokens_original`, `context_truncated` | delivered-context size and whether it was trimmed |
| `prompt_ref`, `output_ref`, `reasoning_ref`, `timeline_ref`, `raw_ref` | paths to the full audit files under `data/results/` |
| `seed`, `temperature`, `max_tokens`, `endpoint`, `harness_commit` | reproducibility |

The app derives **decode tokens/sec** as `output_tokens / (latency_s - ttft_s)`.

## Notes on the current snapshot

- Models: `qwen2.5-7b` and `qwen2.5-coder-7b` (vLLM, all 8 suites) and `qwen3.8:27b-128k`
  (Ollama, five suites complete). The 27B's swebench and swarm are still running on the GPU
  server and will be merged into a later snapshot.
- `repobench` scores near zero for every model and condition: this is a known prompt-framing bug
  (the target file's cursor is not at the end of the prompt), not a real result. Do not read those
  numbers as capability.
- `swebench` shows no objective verdict yet ("none"): its native scoring is a separate pass.
- `objective_pass` is stored as 1 (pass), 0 (fail), or empty (no verdict).

## Refreshing after new data

Copy new run data into `data/results/`, then relaunch with `--rebuild` to re-index. Your grades
and flags in `review.db` are preserved across rebuilds (they are keyed by run id).
