# MCTP Roadmap

Status: research prototype. This roadmap is phased from near-term work that sharpens the
existing evidence to longer-term work that tests whether the architecture scales. It is a plan,
not a set of claims; results are reported as they are produced (see
[EXPERIMENTS.md](EXPERIMENTS.md)).

## Guiding principles

- Compare against strong baselines, not a strawman. A raw transcript is the weakest competitor;
 the real comparison is against a good summary and conventional retrieval, with each baseline's
 full cost counted.
- Do not design the benchmark so MCTP wins. Include small, clean, and easy contexts where MCTP
 is not expected to help, and publish those results too.
- Publish failures and raw data, not just aggregate success rates.
- Reliability is a first-class metric alongside task success and cost.
- Keep the Core protocol deterministic and model-independent; put learned behavior in the
 optional Intelligence Layer (see [DESIGN.md](DESIGN.md)).

## Where things stand

- Core protocol and reference implementation (event-sourced store, selector, hybrid transfer
 with artifact references and retrieve-on-demand), implemented.
- MCTP-Bench harness: ten hand-authored scenarios, episode logging, real tokenizers, a
 deterministic mock runner, and an OpenAI-compatible model runner (`--model`), implemented.
- Evidence so far: single-trial, all-Claude, keyword-scored runs against a transcript baseline.
 Directionally supportive on cost-at-equal-success, with one deliberate failure
 (`hidden_constraint`) showing extraction fidelity is the ceiling.

## Near-term (sharpen the existing evidence)

1. Summary and RAG baselines. Add a `summary` condition (an LLM condenses Agent A's context;
 the summarizer's inference cost is counted) and a `rag` condition (the same source stored and
 fetched by vector retrieval). This is the credibility unlock, it tests MCTP against the
 alternatives it actually competes with. Buildable now on the model runner.
2. Multi-trial and statistics. Run each cell K times and report mean, median, variance,
 confidence intervals, effect size, and significance, broken down per benchmark, per model,
 and per context size. Moves results from single-trial existence checks to statistically
 meaningful evidence.
3. Failure taxonomy. Categorize every failure (information omitted, hallucinated, wrong/stale
 decision retained, artifact unavailable, retrieval failure, MCTP extraction/linking failure,
 model reasoning failure, evaluation/scoring failure) and publish the distribution.
4. Preservation vs. exposure metric. Measure two dimensions separately: how much underlying
 information the system still retains, versus how much it actually sends to the receiver. The
 target profile is high preservation, low active exposure, high relevant exposure. This is a
 distinctive metric the current suite does not yet report.
5. Cross-model sweep via vLLM. Run the suite against open models (Qwen, Llama, and others)
 through the model runner for the first cross-model-family evidence. Deferred until the local
 server is set up.
6. Diagnostic scenario families. Systematize the mechanism probes the current one-off scenarios
 only hint at, as small controlled tests: supersession chains (A superseded by B, modified by
 C, superseded by D, ask for the current constraint and measure stale or contradictory use);
 hidden-constraint sweeps (a critical constraint buried in noise, failed approaches, and
 unrelated files); artifact fidelity (exact source retrieval versus a vague summary); and
 retrieval/recovery (an intentionally insufficient initial packet that a RETRIEVE then
 completes, success, not failure). These complement the OSS suites, which provide scale.

## v0.2 (make it real, not hand-authored)

1. Automatic extraction. Build the extractor that turns a real repository or agent transcript
 into an MCTP graph. This is the central gate: it unlocks external benchmarks and real agent
 capture, and its recall is the system's ceiling. It should have its own fidelity benchmark.
2. External OSS benchmark adapters. Adapt existing suites so MCTP is measured on independent
 tasks with their own scorers: low-context first (HumanEval, MBPP, short QA), then repository
 and long-context suites (SWE-bench / SWE-bench Verified, RepoBench, LongBench-style).
3. Persistent, indexed store. Move beyond the in-memory store to a content-addressed, indexed
 backend (semantic + graph indexes) so state can be queried without a full scan.
4. Intelligence Layer v1. Train the selector/ranker on the episode data the benchmark produces
 (state extraction, relevance ranking, sufficiency prediction), keeping the Core protocol
 unchanged.
5. Agent integration surface. An MCP server exposing `handoff` / `retrieve` (and capture) as
 tools, plus a thin SDK and a tool-layer auto-capture wrapper.
6. Benchmark-as-training-data. Each handoff records Agent A's state, the task, the receiving
 model, the candidate and actually-retrieved context, Agent B's behavior, success or failure,
 the failure type, and what B actually needed, a corpus for training extraction, relevance
 ranking, sufficiency prediction, and adaptive handoff without changing the Core protocol.

## v0.3+ (scale)

1. Multi-agent / swarm benchmarks. Software-engineering, research, data-analysis, long-horizon
 coding, and planning swarms, with objective final metrics (e.g. do the repository's tests
 pass). Vary swarm size (2 to 20 agents) and measure whether MCTP's value grows with it.
2. Context-size stress. Test up to 128K-256K accumulated context; the hypothesis is that
 transcript and summary approaches degrade while MCTP stays comparatively stable.
3. Large persistent-state scaling. Maintain 100M to 1B+ tokens of accumulated state while keeping
 active context small; benchmark retrieval recall/precision/latency and storage/economics
 (hot/warm/cold tiers, dedup, compaction), organized hierarchically (global to project to 
 subsystem to task to decision to evidence to artifact) so retrieval never requires a full scan.
4. Graph-aware retrieval. Compare structured, provenance-aware retrieval against plain vector
 RAG on questions that need relationships, provenance, and rejected-approach history (for
 example, "why did we reject Redis locking six weeks ago?").
5. Cross-model interoperability at scale. Same-model, same-family, and cross-family handoffs
 (open ↔ proprietary) to test whether MCTP is a genuine interoperability layer.

## Metrics we will report

- Task success, and success per transferred token.
- Reliability: variance, p5/p95, failure rate, catastrophic-failure rate, and run-to-run and
 cross-model consistency.
- Cost: total inference across all model calls (including any summarization) plus retrieval and
 infrastructure; end-to-end latency.
- Context: active-context tokens, total tokens, and tokens actually transferred to the receiver.
- Retrieval: precision, recall, latency, cost, artifact-retrieval exactness, and task success
 after zero / one / multiple retrievals.
- Preservation vs. exposure: information retained versus information actually sent.
- The failure-mode distribution, using the taxonomy above.

## Key results to produce

Once the baselines and multi-trial runs exist, the headline graphs are:

1. Task success vs. context size, for transcript / summary / RAG / MCTP.
2. Tokens transferred to the receiver vs. context size.
3. Reliability (variance, failure rate) vs. context size.
4. Task success vs. number of agents.
5. Total cost (all inference + retrieval) vs. task success.

The hypothesis they test: MCTP stays comparatively stable as context grows larger and noisier,
and its advantage increases with swarm size, while transcript and summary approaches degrade.
The eventual target is on the order of thousands of tasks across methods, models, and trials;
that scale is aspirational and gated on automatic extraction and the OSS adapters.

## Reproducibility

A single entry point should run the matrix, for example
`run_benchmark.py --benchmark <suite> --model <name> --agents <n> --conditions transcript,summary,rag,mctp`
, and an analysis step should regenerate the graphs. Publish raw per-run JSON/CSV, aggregated
results, benchmark configurations, model versions, prompts, seeds, evaluator versions, and the
exact MCTP configuration, so others can reproduce and extend the results.

## The claim we are testing

Whether explicitly structured, provenance-aware state transfer lets multiple AI agents
collaborate more reliably and efficiently than raw transcripts, LLM summaries, or conventional
retrieval, across models, tasks, context sizes, swarm sizes, and persistent-state sizes. The
strongest version of the result would hold even when the comparison is deliberately fair, and
would show MCTP's advantage growing as context becomes larger, noisier, and more distributed.
It is an open question, not a settled result.

In one line: build MCTP, benchmark realistic agent workflows against strong baselines, measure
reliability, context, cost, retrieval, and scaling, classify the failures, use them to improve
extraction and selection, then re-run, publishing all data and methodology.
