# ADR 0001: Walking Skeleton Architecture for End-to-End Governance

## Status
Accepted

## Context
Pre-publication compliance and brand governance require multi-layer evaluation across heterogeneous modalities: raw copy, rich documents (DOCX, PDF, HTML), and graphical campaign banners. Evaluating these assets involves multiple algorithmic paradigms, including deterministic regex token matchers, Sharma-Wu-Dalal CIEDE2000 color distance calculations, Otsu text segmentation, WCAG 2.1 relative luminance, Z3 SMT constraint solving, and NLI semantic entailment.

Without an end-to-end integration slice established at the project inception, developers building individual checks risk diverging on AST contracts, locator coordinate systems (character spans vs image pixel bounding boxes), SSE stream formats, finding resolution semantics, and audit persistence.

## Decision
We adopted the **Walking Skeleton** architectural pattern: the thinnest possible production slice connecting every layer from inbound document ingestion to final cryptographic audit persistence:
1. **Parsers**: Ingest diverse formats (`.txt`, `.md`, `.docx`, `.pdf`, `.html`, `.png`, `.jpg`) and produce a unified, immutable `ContentAST` composed of content-hash addressed nodes (`TextNode`, `ImageNode`, `TableGridNode`).
2. **Engine**: An async runner that dispatches registered synchronous checks to `asyncio.to_thread` worker threads with per-check timeout isolation and streams findings progressively via Server-Sent Events (SSE).
3. **Domain & Checks**: Auto-registering check plugins inheriting from `Check`, returning deterministic finding records with strongly-typed evidence payloads.
4. **Workflow State Machine**: A table-driven, role-gated state transition model (`Status`: `draft` → `in_review` → `changes_requested` → `approved` → `published`) enforcing a hard blocker gate (409 Conflict if open blockers remain during approval/publishing).
5. **Ledger**: Deterministic SHA-256 hash-chained event sequencing and RFC 9162 Merkle tree transparency logging.
6. **Frontend**: React SPA consuming SSE findings, inline ProseMirror/Tiptap text highlight annotations, SVG pixel bounding box overlays, and TanStack Query server-state cache management.

## Consequences
- **Positive**: Hard integration challenges (SSE streaming, coordinate mapping, state machine transitions, audit chaining) are solved once at the foundation, allowing domain checks and parsers to be authored independently without modifying engine orchestration.
- **Positive**: Clean contract boundaries prevent regressions when adding new check types.
- **Negative**: Initial architectural setup required strict upfront discipline across AST definitions and schema models before individual check logic could be implemented.

## Alternatives Considered
- *Monolithic check script*: Rejected because it prevents progressive live UI streaming, lacks isolated timeout handling, and couples checks tightly to I/O and storage.
- *Microservices per check*: Rejected due to high inter-process communication latency, operational complexity, and serialization overhead when passing large AST document graphs.
