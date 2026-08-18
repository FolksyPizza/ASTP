# MCTP — Model Context Transfer Protocol

**Status:** Design draft (v0.1 planning)
**Companion repo:** MCTP-Bench — the evaluation harness (§8). Sibling repo at
`../MCTP-Bench` / [github](https://github.com/FolksyPizza/MCTP-Bench). Has a working v0.1
harness: `episode` records (§6.2), flat-vs-mctp conditions, scoring, `python3 run.py`.

---

## 1. Overview

MCTP is an open protocol and system for the efficient exchange, storage, retrieval,
and auditing of AI task state. It provides a **persistent state layer** between models
and agents so that context can be transferred as *structured state* rather than as raw
conversation, logs, or bulk summaries.

```
Model
 |
MCTP  (state layer: extract → store → select → transfer → audit)
 |
Knowledge / Memory / Agents / Tools
```

**Core objective:** provide the *minimum sufficient context* for another model or agent
to continue work — minimal, without leaving anything out. Computing that set is the
central research contribution, not a solved serialization problem.

MCTP is **lossy by design**: it targets *bounded sufficiency*, not completeness.

---

## 2. Non-Goals

MCTP does **not** attempt to:

- replace model reasoning
- solve all AI memory
- eliminate retrieval
- perfectly understand every task
- replace human engineering judgment
- guarantee lossless transfer (it is deliberately lossy/bounded)
- replace version control or the codebase as source of truth
- act as a low-latency IPC bus (it is a state layer, not a message queue)
- create a universal AI architecture
- guarantee perfect context prediction

MCTP **aims to**:

- reduce unnecessary context transfer
- preserve important state
- improve agent collaboration
- improve auditability
- optimize cost/performance

---

## 3. Architecture

### 3.0 Layering: Core MCTP vs Intelligence Layer

MCTP is split into two layers so the protocol never depends on any learned component.

**Core MCTP — must exist no matter what (the foundation):**
- Protocol
- State representation
- Memory storage
- Audit trail
- Retrieval (incl. a deterministic cold-start baseline selector)
- Provenance
- Context transfer

**Intelligence Layer — optional, learned, sits *on top of* Core:**
- Context ranking
- Sufficiency prediction
- Retrieval planning
- Cost optimization
- Adaptive feeding (§7)
- Predictive retrieval

The Intelligence Layer is an **add-on harness**, not part of the protocol. Core must be
fully usable — ingest, store, audit, retrieve, transfer — with the deterministic baseline
selector and *zero* learned models. The learned components only replace/augment the
baseline selector's ranking. This is also the protocol/implementation boundary: **only
Core is the portable protocol.**

#### Repository structure
```
MCTP/
  PLAN.md
  docs/schema-v0.1.md      # v0.1 wire/state schema
  core/                    # Core MCTP — the protocol + reference implementation
    mctp/                  # model, store (event log + graph), retrieval, transfer
  intelligence/            # Optional Intelligence Layer (separate, add-on)
  bench/                   # rough viability probe + (later) MCTP-Bench harness
```

### 3.1 Two model roles (extractor + selector)

Two model roles, kept deliberately separate — they have different eval criteria and
different risk profiles.

#### Extractor (ingestion)
Raw agent context → structured MCTP nodes (task / artifact / entity / decision / relation)
with provenance. Runs **online and incrementally** as an agent works, emitting events
that materialize the graph. This is where hallucination and provenance-corruption risk
live. **Its recall is the ceiling on the whole system** — anything ingestion drops, the
selector can never recover.

#### Selector (transfer / retrieval)
Materialized graph + task + budget → **bounded packet** of existing nodes. Extractive
(chooses existing provenance-tagged nodes), not abstractive, for v0.1 — so every
transferred item has a source and "did it leave something out" is a measurable recall
problem. An abstractive "bridge note" layer may be added in v0.2.

Retrieval and handoff are the **same operation** with different seeds:
`select(seed, budget) → ranked subgraph`.

### 3.2 Selection as negotiation (system + Agent B)
The selector is not solely the system *or* Agent B — it is a negotiation:

- System **pushes** a predicted-relevant packet (proactive; see §7 adaptive feeding).
- B **pulls** more when it detects insufficiency (queries the persisted graph).
- The gap between push and pull is the **training signal** (§6).

**Invariant:** what B pulls is the *persisted MCTP graph*, never Agent A directly. A is
not guaranteed to exist after handoff. The graph must be sufficient on its own.

### 3.3 Transfer modes (selector policy)
Given (task, budget, uncertainty, A-availability), the selector picks a mode:

- **A — Full context** (broad; for global-understanding tasks)
- **B — Compressed context**
- **C — Structured state**
- **D — Send nothing yet; allow retrieval** (against the persisted graph)
- **E — Hybrid**

**Rejection mode** is first-class: the selector may *refuse to compress* when the task
needs global understanding, and provide broader context instead. Example:

```
Decision: Do not compress.
Reason:   Task requires global understanding.
Action:   Provide broader context.
```

### 3.4 Native integration (v0.3 concept)

The most ambitious version: MCTP is attached directly to the model/agent environment with
access to current context, task state, agent actions, and retrieval history.

```
1. Agent works normally.
2. MCTP observes context / state / actions / retrieval history.
3. MCTP creates a structured snapshot (extractor).
4. MCTP determines what should be transferred (selector).
5. Next model receives optimized context — only high-value information, not everything.
```

This depends on the **feedback/observation interface** (§6.2) being defined first — it is
the input contract for both the v0.1 API-adapter path and the v0.3 native path.

### 3.5 Hybrid context delivery (default composition)

MCTP does not choose between full-raw and over-compressed. The default packet composes
three delivery tiers:

- **Always provide (inline):** high-value state — task objective, current state, active
  decisions, constraints, critical dependencies.
- **Provide as references:** artifacts (source files, docs, logs, configs) as
  `{path, hash, language, symbols, deps}` — enough to locate and reason about, not the bytes.
- **Retrieve on demand:** large/expensive content (full source, large outputs, history)
  fetched only if the receiver asks (`RETRIEVE <id>` → blob store).

Goal: *don't transfer everything, don't over-compress — transfer enough to continue.* A
targeted retrieve is **expected behavior**, not a miss; a fallback to the raw codebase for
something un-referenced is the miss (§6.2).

---

## 4. Data Model

### 4.1 Semantic core (every adapter must round-trip losslessly)
```
node { id, type, provenance, payload }
edge { id, from, to, relation_type, provenance }
```
Model-specific richness lives in the opaque `payload` (best-effort round-trip).

### 4.2 Node types
- **Task** — current objective (fix bug, research, implement feature)
- **Artifact** — a resource (file, code, document, dataset), stored as a **reference**, not
  a prose summary: `{path, content_hash, language, symbols, dependencies, tokens}`. Full
  bytes live in the blob store and are fetched on demand (§3.5). Summaries lose the
  implementation detail the receiver may need — see the empirical finding in §8.6.1/§8.6.2.
- **Entity** — important object (function, class, concept, system)
- **Decision** — a choice: decision + reasoning + evidence + provenance + verification
- **Relation** — connection (see closed vocabulary below)

### 4.3 Relation vocabulary (CLOSED for v0.1)
`calls`, `depends_on`, `modifies`, `supersedes`, `contradicts`, `derived_from`, `relates_to`

A closed set is required for the graph walker, eval reproducibility, and cross-model
adapters. Extend deliberately, never with free text.

### 4.4 Identity
- **Immutable artifacts** (files, tool outputs, evidence): content-addressed (hash) →
  free dedup, immutability, verifiability.
- **Mutable conceptual nodes** (Task, Decision, Entity): UUID + version chain.
- **Entity coreference:** anchor to `content-hash(artifact) + symbol locator` so two
  references to the same real thing resolve to the *same ID by construction*. Only
  abstract entities with no artifact anchor use fuzzy/embedding coref. This prevents
  graph **fragmentation** (one thing → many nodes → split edges → silent under-recall)
  and **collision** (distinct things merged) as the graph grows.

### 4.5 Provenance & trust
Every important node carries: source, agent, model, timestamp, confidence, and
`verification_status ∈ { asserted, tool-verified, human-verified, contradicted }`.

Decouple two concerns:
- **Convergence policy** — which concurrent write survives structurally (e.g. LWW / CRDT).
- **Trust ranking** — what the selector presents to B: prefer verified > asserted, and
  **surface contradictions** rather than silently taking the newest. Newer ≠ truer.

### 4.6 Retraction vs maintenance (distinct axes)
- **Invalidation** — "this decision is now false": a first-class `supersedes` / `contradicts`
  event. The materialized view computes "currently believed?"; the selector filters
  contradicted nodes by default; history retains them for audit.
- **Maintenance** — "rarely used → demote": deterministic, threshold-based (§5.4).

---

## 5. Storage Architecture

Three tiers. **Tiering primarily bounds the search space, not just cost.**

### 5.1 Active state
Hot working set. Searched first. Fast retrieval.

### 5.2 Historical memory
Old decisions, experiments, previous approaches. Searched only on an active-tier miss.

### 5.3 Audit log
Complete event history. Used for replay, debugging, reproducibility, and **truth
enforcement**. Essentially never searched at retrieval time → can be compressed / cold-stored.

### 5.4 Maintenance (deterministic, no model)
Hard-threshold promote / demote / archive on a **composite score
(graph-centrality + recency + frequency)** — never frequency alone, or cold-but-critical
nodes get wrongly demoted and hubs get promoted forever. Actions are themselves audited
events. Information is archived/tagged/deprioritized, not deleted.

### 5.5 Scaling hazards to design against
- **Event-log compaction** — periodic materialized snapshots; never replay from genesis.
- **Hub fan-out** — edge weighting + bounded-hop expansion so popular nodes don't explode the walker.
- **Incremental indexing** — ANN index (HNSW-style) updated per-event, never full rebuild.

---

## 6. Learning Loop (the research core)

The training signal comes free from the audit log:

1. Selector emits packet **P** for B.
2. B works; any node B must **pull from the persisted graph that wasn't in P** is logged
   as a **miss (M)**. (If B falls back to re-reading the *codebase*, that is objectively
   far more expensive and counts as a severe miss.)
3. `M` = ground-truth "should have included" labels.
4. Nodes in `P` that B never used = over-inclusion = wasted tokens.

Two-sided objective, no human labeling required for the base loop:
- **Recall loss** ← minimize misses `M`
- **Precision loss** ← minimize unused nodes in `P`

**Why a dedicated selector beats "ask A's model to summarize":** A's model shares A's
blind spots. A separate selector trained on cross-episode miss data learns
*population-level* patterns ("tasks of this shape also need X even when A never mentioned
it") — this is what lets the system include what B would have left out.

### 6.1 Human labeling layer
- **Uncertainty-triggered** — the selector emits confidence; low-confidence handoffs go to
  human review (active learning: cheapest, highest-value labels near the decision boundary).
- **Fully-labeled gold set** — held out for evaluation (§8).

### 6.2 Feedback signals & the observation interface

Signals collected after B receives context, and the **observable event** each maps to.
Attention is invisible in API settings, so "used/ignored" must be a behavioral proxy, not
true attention:

| Signal | Observable proxy | Label |
|--------|------------------|-------|
| requests more info | B issues an MCTP pull not in packet P | **miss** (recall) |
| searches for missing info | B re-reads the codebase / greps despite P | **severe miss** (recall) |
| ignores provided info | node in P never referenced or acted on | **over-inclusion** (precision) |
| completes the task | task outcome check passes | outcome label |

Training data:
- **Successful transfers** — what was provided + task outcome + model behavior.
- **Failed transfers** — missing info / unnecessary info / incorrect prioritization.

**Decision (v0.1 operational contract).** Each handoff produces one appended `episode`
record; no attention data is required.

```
episode {
  task, packet_node_ids, context_tokens,
  pulls:      [node_id]      # MCTP retrieval calls B made that were NOT in the packet -> miss
  codebase_reads: int        # file-read/grep tool calls B made -> severe miss
  used_node_ids: [node_id]   # packet nodes B referenced in output or acted on
  outcome:    pass|fail       # task-specific deterministic/AI checker
}
```

Operational definitions (all observable, no attention needed):
- **miss** ← a `pull` event (B queried the graph for something not in the packet).
- **severe miss** ← a `codebase_reads` event (B fell back to raw source).
- **used** ← packet node id appears in B's output, or in a tool call B issued (string/id
  match, backed by a light LLM judge for paraphrase). Packet nodes not used = over-inclusion.
- **outcome** ← per-task checker (deterministic where possible, else AI eval).

Recall label = `pulls ∪ codebase-derived facts`; precision label = `packet \ used`. This is
the training signal for §6; it is also the input contract for native integration (§3.4).

**Label vocabulary** (each packet item, derived from the observable signals above):
- **USED** — evidence the context influenced behavior (explicit reference, a correct action
  requiring it, or a known mistake avoided).
- **AVAILABLE_UNUSED** — provided but no evidence it mattered → precision cost.
- **INSUFFICIENT** — needed information was not provided → recall cost (pull / codebase read).
- **MISLEADING** — provided information caused *incorrect* behavior → the most costly label;
  the target of staleness filtering (superseded/contradicted nodes) and trust ranking (§4.5).

---

## 7. Adaptive (Proactive) Context Feeding

**Intelligence Layer (optional add-on harness — lives in `intelligence/`, not Core.)**

Before being called, MCTP observes the agent's activity, predicts what may be needed,
prepares it, and *suggests* it:

```
MCTP:
You are modifying NodeTransfer.

Likely relevant:
 - LeaseManager
 - PartitionMap
 - Previous migration bug #43

Would you like this loaded?
```

This is the proactive push side of the negotiation. Guardrails: suggest only above a
confidence threshold (avoid alarm fatigue), and make declining cheap.

---

## 8. Evaluation (MCTP-Bench)

### 8.1 Metrics
- **Precision (gold, benchmark only):** minimal sufficient set found by **ablation** —
  drop a node, re-run B; if B still succeeds it was unnecessary.
  `precision = |P ∩ gold| / |P|`, `recall = |P ∩ gold| / |gold|`.
- **Proxy precision (online, at scale):** fraction of transferred nodes B actually reads.
- **Headline metric:** **total tokens to task completion, including recovery retrievals**
  (codebase re-reads included — that recovery cost is where structure beats a flat file).

### 8.2 Baseline fairness
MCTP context is produced by extra compute. Hold task + total token budget constant, and
**report two numbers**:
- **Marginal cost at handoff** (selector only; valid if extraction is amortized across A's session).
- **Total cost including extraction** (conservative).

Compare against a **plain text-file** handoff baseline under identical budget.

### 8.3 Benchmark categories
- **Single agent** — normal context vs MCTP context (success, tokens, latency)
- **Agent handoff** — A works, B continues (state-transfer quality, missing info, extra retrieval)
- **Multi-agent** — collaboration through MCTP (communication efficiency, duplicate work, final quality)

### 8.4 Evaluation methods
- **Deterministic** — code tests, compilation, math correctness
- **AI evaluation** — explanations, architecture, research quality
- **Human review** — required before publishing major claims

### 8.5 Metric taxonomy (MCTP vs baseline: raw context / transcripts / normal summaries / standard retrieval)
- **Efficiency** — token usage, cost, latency
- **Agent performance** — task completion, correctness, human evaluation
- **Agent behavior** — tool calls, unnecessary file reads, additional searches, recovery attempts
- **Context quality** — relevance, stale information removed, missing-information rate

### 8.6 Prototype result (recorded — mechanics probe, `bench/viability_test.py`)
Flat structured context **446 tokens** → MCTP packet **385 tokens** (~**13.7%** reduction).

Interpretation — this **does NOT prove** end-to-end agent improvement, better task
performance, or final compression capability. The baseline is deliberately lean (node
contents only, no transcript filler), so 13.7% is a **floor**. It **does demonstrate**:
structured representation is viable, stale info is removed, irrelevant info is filtered,
and important relationships are preserved. Model-in-the-loop tests are required next.

### 8.6.1 Two-model handoff probe (recorded — `bench/handoff/`)
Two isolated Claude "Agent B" instances, identical neutral question ("fix bug #43"), blind
to everything but their assigned context. Condition A = raw Agent-A transcript (~**815**
tokens: file dumps, benchmark output, the *abandoned* locking approach). Condition B = MCTP
packet (~**401** tokens). ~**51% context reduction.**

Result: **correctness parity** — both B's independently gave the correct mechanism
(time-bounded leases), the correct ordering constraint (renew lease *before* copying node
state), and correctly reported distributed locking as *rejected* (neither was misled by the
stale approach). This supports the v0.1 thesis: *maintain performance at roughly half the
context*.

Finding: the MCTP condition additionally requested the concrete NodeTransfer.java migration
code path, because the `art_nodetransfer` node stored a prose summary rather than the code,
while the transcript carried the actual method body. This is an extraction-fidelity miss
(open question #8): the selector under-included code-level detail. Design implication:
artifact nodes must carry or reference the real artifact (content-addressed pointer) rather
than a lossy summary. Caveats: single trial per condition, all Claude models, one hand-built
scenario, and a task already solved by Agent A; this measures staleness removal and token
cost, not general compression or cross-model-family transfer.

### 8.6.2 Re-run after artifact references (recorded — fix confirmed)
Implemented artifact references (`assert_artifact` → `{path, hash, language, symbols}` +
blob store + `RETRIEVE <id>` retrieve-on-demand) and re-ran the MCTP condition (~411 tok
packet). Outcome:
- Using the reference **symbols** alone, B pinpointed the exact change site — `migrate()`,
  before `copyNodeState()` — with no full source yet. The old vague "I'd need the code" gap
  became a **precise, targeted** `RETRIEVE art_nodetransfer` (designed behavior, not a miss).
- After the one targeted retrieve was fulfilled, B produced a **correct, confident patch**
  (renew lease + setOwner + verify `isOwner` before copy) and reported "nothing missing."

Confirms the §8.6.1 finding was a representation defect, not a selector defect, and that
hybrid delivery (§3.5) resolves it: references + one cheap pull replaced a full inline dump.

### 8.7 Planned experiment — coding-agent handoff
Large codebase (e.g. Folia/Minecraft infra). Agent A investigates an issue and creates
context; Agent B solves it. Baseline = full transcript; MCTP = structured transfer.
Measure: tokens, correctness, time, tool calls, file reads.

---

## 9. Protocol Goals

Versioning, serialization, validation, capability negotiation, model adapters, security.

**Protocol vs implementation boundary:** MCTP-the-format and MCTP-the-selector-model are
separable — only the *format* is a portable protocol. Generalization across model families
is claimed only for the format.

### Model support
- **Open models** (Qwen, Gemma, Llama, DeepSeek, Kimi, GLM): fine-tunable for native MCTP.
- **Closed models** (GPT / Claude / Gemini): via adapters.
```
MCTP Controller → API Adapter → Closed model
```

---

## 10. Security / Threat Model (at minimum, acknowledged in v0.1)

MCTP state is attacker-controllable input to the *next* model and **persists/propagates**
across agents — a poisoned Decision node is a stored prompt injection with blast radius =
every future agent that retrieves it. Decisions to make (mitigation may be v0.2):

- Treat MCTP content as **data, not instructions** in the consumer's prompt (structural separation).
- **Provenance-gated trust** — don't act on low-trust asserted content as instruction.
- **Sign provenance** so an asserter cannot be forged across trust boundaries.
- **Subgraph access control** for cross-org transfer.
- **Namespace isolation** across projects (enforced, not soft tags) to prevent leakage.

---

## 11. Open Questions (decide before / during implementation)

**Foundational (before code):**
1. Identity scheme + entity coreference — content-address + locator (§4.4). ✅ decided
2. Semantic core + closed relation vocabulary (§4.3). ✅ decided
3. Retraction as a first-class event (§4.6). ✅ decided
4. Cold-start heuristic — implemented as the Core baseline selector (bounded k-hop over
   the believed subgraph). Doubles as benchmark control. ✅ decided (built)
5. Selection contract = negotiation (push + pull), objective = two-sided recall/precision. ✅ decided
6. Trust stance: descriptive vs operative provenance (§4.5). ✅ decided (decoupled)
7. Benchmark fairness: constant budget, report marginal + total (§8.2). ✅ decided

**Still open:**
8. **Extraction fidelity eval** — how to measure ingestion recall (the system's true ceiling).
9. **Break-even point** — MCTP's own cost vs context saved; net-negative for short tasks.
   Target regime = long-running / multi-agent. State break-even as a research question.
10. **Concurrency semantics** — CRDT vs single-writer lease (deferred).
11. **Retrieval reproducibility** — log "what was sent" (likely enough) vs "reproducibly why".
12. **Adaptive-feeder eval** — false-positive/alarm-fatigue rate.
13. **Feedback/observation interface** — behavior → clean recall/precision labels.
    ✅ decided (v0.1): `episode` record with pulls/codebase-reads/used/outcome (§6.2).

---

## 12. Roadmap

### v0.1 — prove structured transfer is useful
Minimal path: semantic-core schema · append-only event log · materialized "current state"
view · one trivial cold-start selector baseline · one agent-handoff benchmark vs text file.

- Define protocol format, schemas, core objects
- Event logging (assert / supersede / contradict / retrieve / transfer)
- Basic storage + basic retrieval
- Simple agent-handoff demo
- **Avoid:** training large models, complex autonomy, premature optimization, tiering,
  nightly maintenance, multi-model adapters (all v0.2+)

**First goal:** show structured state transfer beats raw context *at equal cost* on a
handoff task.

### v0.2+
Trained selector (learning loop), 3-tier storage + maintenance, adaptive feeding,
abstractive bridge notes, multi-model adapters, concurrency model, security mitigations.

### v0.3 — native integration (§3.4)
MCTP attached to the agent environment; online snapshot + optimized delivery; predictive
retrieval. Gated on the feedback/observation interface (§6.2).

---

## 13. Research Questions

**Primary:** Can structured AI state transfer maintain or improve performance while
reducing context size?

**Secondary:**
- How much token reduction is possible?
- Does MCTP generalize across model families?
- Can agents collaborate more effectively?
- Can historical AI state improve future performance?
- Can MCTP improve reliability and auditability?
- Where is the cost break-even vs. raw context?

**Central question:** *Can structured, intelligent context transfer let AI agents
communicate more efficiently than raw context transfer while maintaining task performance?*

**Any outcome is useful research:**
- **Success** — improved efficiency, lower cost, better collaboration.
- **Partial** — works for specific regimes (coding handoff, long-running agents).
- **Failure** — insight into the limits of context-transfer systems.
