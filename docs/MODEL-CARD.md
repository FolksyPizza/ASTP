# Model Card, ASTP Intelligence Layer (learned selector/reranker)

Status: not yet trained. This card is published in advance so the training data and intended use
are declared before any model exists, and will be completed when a model is released.

## What the model is

The optional ASTP Intelligence Layer includes a learned reranker / sufficiency predictor that
scores and prunes the candidate set produced by the deterministic Core selector (see
[ARCHITECTURE.md](ARCHITECTURE.md)). It is **not** a language model: it is a lightweight ranking
model over provenance-tagged candidate features (node type, relation distance, recency,
verification status, and similar). It can only reorder or drop candidates the deterministic walk
already surfaced, it never invents context, so the system stays extractive and auditable, and
the model's contribution is measured strictly as the delta above the deterministic floor.

## Training data, synthetic

The reranker is trained on **synthetic data**. The training signal is the per-node episode labels
collected by ASTP-Bench (which packet nodes the receiver used vs. left unused to precision; nodes
the receiver had to retrieve or read from source to recall/misses). The cleanest, ground-truth
labels come from the **synthetic control suites**, where the correct state and the deliberate
traps are known by construction:

- The in-house control scenarios (hand-authored graphs with known relevant/irrelevant nodes and
 superseded decisions).
- The generated `multifile` and `swarm` suites, produced by `scripts/generate_synthetic.py` from
 parametric templates. Every generated task is marked `"synthetic": true` in the dataset.

We state this plainly for transparency: **the learned selector is trained on synthetic episodes.**
Any evaluation on independent, non-synthetic tasks (the OSS suites: HumanEval, MBPP, GSM8K,
SWE-bench, RepoBench, LongBench) is reported separately as held-out evaluation, never mixed into
training. When a model is released, this card will record the exact training-set composition,
counts, and the train/eval split.

## Intended use and limits

- Intended: reranking Core-produced candidates for agent-to-agent state handoff.
- Not intended: as a general retrieval or memory system, or as a source of new context.
- The system's ceiling is extraction/linking fidelity, not the reranker: if a needed node is not
 in the candidate set, no reranker can recover it (see the `hidden_constraint` control).

## Evaluation

Reported against the deterministic Core selector as the baseline, on held-out non-synthetic
suites, with task success from objective scorers or the cross-review judge ensemble, and behavior
metrics (tokens transferred, retrievals, cost) logged alongside. See the benchmark design in the
companion repository.
