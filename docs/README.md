# CanonGate Documentation

This directory contains architectural specifications, presentation decks, and Architecture Decision Records (ADRs) for the **CanonGate** platform.

---

## 📑 Core Documentation & Presentation Decks

* 📊 [**System Architecture Diagram (PDF)**](./CanonGate_Architecture_Diagram.pdf)
  Comprehensive diagram illustrating the ingestion pipeline, AST normalization, multi-tiered checking engines (Tier 1 deterministic, Tier 1.5 Z3 SMT arithmetic, Tier 2 NLI fact verification, Tier 3 constrained rewriter), and the RFC 9162 Merkle tree audit ledger.

* 📑 [**Pitch Deck Presentation (PDF)**](./CanonGate_Pitch_Deck.pdf)
  Executive presentation covering product overview, regulatory problem statement, automated claim governance, competitive advantages, and implementation roadmap.

---

## 🏛️ Architecture Decision Records (ADRs)

* [**ADR 0001: Walking Skeleton**](./adr/0001-walking-skeleton.md) — Thin end-to-end slice through all system layers.
* [**ADR 0002: Layered Import Boundaries**](./adr/0002-layered-import-boundaries.md) — Strict import hierarchy enforced by `import-linter`.
* [**ADR 0003: Local-First SQLite with Postgres Compatibility**](./adr/0003-local-first-sqlite-with-postgres-compatibility.md) — Portable persistence architecture.
* [**ADR 0004: Tiered Governance Execution Pipeline**](./adr/0004-tiered-governance-execution-pipeline.md) — Tier 1, 1.5, 2, and 3 execution model.
* [**ADR 0005: Hash-Chained Audit and Merkle Transparency**](./adr/0005-hash-chained-audit-and-merkle-transparency.md) — Cryptographic audit trails and RFC 9162 transparency trees.

---

## 🔗 Related Resources

* [Root README](../README.md)
* [AI Agent Guidelines (AGENTS.md)](../AGENTS.md)
* [Feature Matrix & Gap Analysis](../gap_analysis.md)
