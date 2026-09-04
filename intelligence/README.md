# ASTP Intelligence Layer (optional add-on)

**Not part of the Core protocol.** Everything here sits *on top of* Core ASTP and is
optional, Core is fully usable (ingest, store, audit, retrieve, transfer) with the
deterministic baseline selector and zero trained models.

Components planned here (all replace/augment Core's baseline, none change the protocol):

- **Context ranking**: learned reranker over the candidate subgraph Core retrieves.
- **Sufficiency prediction**: predict whether a packet is enough before B runs; emit a
 confidence used to trigger human labeling (active learning).
- **Retrieval planning**: choose transfer mode A-E (full / compressed / structured /
 retrieve-on-demand / hybrid) per task, incl. rejection mode ("do not compress").
- **Cost optimization**: trade packet size against predicted miss cost.
- **Adaptive feeding**: proactively observe an agent, predict likely-relevant state, and
 *suggest* loading it ("You are modifying NodeTransfer. Likely relevant: LeaseManager…").
- **Predictive retrieval**: prefetch before B asks.

## Training signal

The Core audit log is the training data: for each handoff, nodes B had to pull that were
**not** in the packet = misses (recall labels); packet nodes B never used = over-inclusion
(precision labels). See the feedback interface in [../docs/DESIGN.md](../docs/DESIGN.md).
