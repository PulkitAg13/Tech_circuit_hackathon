# CanonGate — Autonomous Pre-Publication Brand & Claim Governance Platform

[![Backend Tests](https://img.shields.io/badge/backend%20tests-98%20passed-brightgreen.svg)]()
[![Code Style](https://img.shields.io/badge/code%20style-ruff-000000.svg)]()
[![Architecture](https://img.shields.io/badge/architecture-import--linter%20enforced-blue.svg)]()
[![Frontend](https://img.shields.io/badge/frontend-Vite%20%2B%20React%20%2B%20TS-61dafb.svg)]()

> **CanonGate** is a pre-publication brand, clinical, and regulatory claim governance engine. It validates multimodal campaign copy, linearized tables, HTML, `.docx`, and banner images against signed brand canons and regulatory rules (ASCI, RBI, CCPA, WCAG 2.1) before publication.

---

## 📌 Executive Architecture & Pitch Deck

| Document | Description | Direct Links |
| :--- | :--- | :--- |
| **System Architecture Diagram** | Complete technical architectural overview, end-to-end data pipeline, SMT verification, and RFC 9162 Merkle tree ledger | [**Download PDF (Root)**](./CanonGate_Architecture_Diagram.pdf)<br>[**View in `docs/`**](./docs/CanonGate_Architecture_Diagram.pdf) |
| **Pitch Deck Presentation** | Product vision, market problem, automated regulatory compliance, competitive differentiation, and business model | [**Download PDF (Root)**](./CanonGate_Pitch_Deck.pdf)<br>[**View in `docs/`**](./docs/CanonGate_Pitch_Deck.pdf) |

---

## 🏛️ System Architecture

```
                             Multimodal Inputs
            (.txt, .md, .docx, .pdf, .html, .png, .jpg banners)
                                    │
                                    ▼
                     Content Parsers & Normalizers
            (TableGrid, Linearizer, OpenCV SIMD Banner OCR)
                                    │
                                    ▼
                         ContentAST (SHA-256 Nodes)
                                    │
    ┌───────────────────────────────┴──────────────────────────────┐
    │                                                              │
    ▼                                                              ▼
Tier 1: Deterministic Engine                         Tier 1.5: SMT Claim Algebra
• terminology.banned (POS / UPOS)                    • Z3 Real SMT Solver (Thread-Safe)
• visual.palette_drift (CIEDE2000 ΔE00)              • SymPy Interval Arithmetic
• visual.logo_orb (OpenCV ORB + RANSAC)              • SciPy HiGHS Linear Programming
• voice.readability (Flesch-Kincaid)                 • Drip Pricing Contradictions
• trigger.disclaimer (Mandatory Disclaimers)         • RBI KFS / Expiry Windows
• accessibility.contrast (WCAG 2.1 AA/AAA)
• unicode.confusable (TR39 Homoglyphs)
• security.hidden_text (OWASP LLM01)
    │                                                              │
    └───────────────────────────────┬──────────────────────────────┘
                                    │
                                    ▼
                   Tier 2: Claim Slot NLI Verification
                   • Hybrid BM25 + Vector Retrieval
                   • QASem Slot Decomposition
                   • ONNX MiniCheck NLI Scoring
                   • ASCI Substantiation Routing
                                    │
                                    ▼
                Tier 3: Constrained Surgical Rewriter
                • RapidFuzz Wagner-Fischer Edit Ceiling (≤35%)
                • Microsoft Presidio DPDP 2025 PII Scrubber
                • Automatic Tier 1 & Tier 2 Re-Verification
                                    │
                                    ▼
            RFC 9162 Merkle Tree Audit Ledger & Workflow
            • Immutable SHA-256 Hash Chain
            • Table-Driven Role Transitions (Creator / Reviewer / Admin)
            • Deliberate Override Friction Telemetry (Krippendorff's α)
            • C2PA X.509 Cryptographic Manifest Signing
```

---

## 🚀 Quickstart

### 1. Backend Setup (FastAPI + Python 3.13)

```bash
cd backend

# Install dependencies via uv
uv sync --extra dev

# Run test suite (98 tests must pass)
uv run pytest -q

# Code quality & import boundary checks
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run import-linter lint

# Start FastAPI server
uv run uvicorn canongate.api.app:app --reload --port 8000
```
Interactive API documentation will be available at `http://127.0.0.1:8000/docs`.

### 2. Frontend Setup (Vite + React + TypeScript)

```bash
cd frontend

# Install packages
npm install

# Run static linter & build
npm run lint
npm run build

# Start local development server
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 🛡️ Key Platform Capabilities

1. **Deterministic Speed (<5ms):** Terminology filtering, Sharma-Wu-Dalal CIEDE2000 color drift, OpenCV ORB homography distortion, and WCAG 2.1 luminance contrast checks.
2. **SMT Arithmetic Proofs:** Zero hallucination. Uses Z3 SMT and SymPy interval arithmetic to detect impossible financial promises (e.g., hidden APR drip pricing, interest rate contradictions).
3. **Multi-Format Parsers:** Native ingestion of `.docx`, `.pdf`, `.html`, Markdown tables, and image banners with OpenCV morphological bounding boxes.
4. **Interactive Review Studio:** Tiptap ProseMirror editor highlighting violation spans directly on campaign text, with inline comment threads, cognitive blocker locks, and 1-click surgical rewrites.
5. **Cryptographic Proof of Governance:** Every action generates an inclusion proof in an RFC 9162 Merkle tree with exportable audit certificates (`/api/submissions/{id}/certificate`).
6. **Canon Evolution & Telemetry:** Monitors reviewer friction, calculates Krippendorff's alpha inter-annotator agreement, and auto-proposes Canon v1.1 Pull Requests.

---

## 📂 Repository Structure

```
├── CanonGate_Architecture_Diagram.pdf   # Technical Architecture Diagram
├── CanonGate_Pitch_Deck.pdf              # Investor & Product Pitch Deck
├── AGENTS.md                            # AI Agent pair programming guide
├── gap_analysis.md                      # Feature completeness & gap audit
├── backend/                             # FastAPI backend
│   ├── src/canongate/
│   │   ├── domain/                      # Pure frozen Pydantic models (no I/O)
│   │   ├── engine/                      # Execution runner, registry, conformal prediction
│   │   ├── checks/                      # 13 automated governance checks
│   │   ├── parsers/                     # Multimodal AST parsers (.docx, .pdf, banner)
│   │   ├── canon/                       # YAML loader, compiler, impact & PR generator
│   │   ├── ledger/                      # RFC 9162 Merkle tree, audit chain, C2PA
│   │   └── api/                         # FastAPI routes & dependencies
│   └── tests/                           # Complete test suite (98 integration tests)
├── frontend/                            # Vite + React + TypeScript SPA
│   ├── src/features/submissions/        # Review Studio, Tiptap editor, Findings & Audit
│   ├── src/features/auth/               # Role-based auth (Creator / Reviewer / Admin)
│   └── src/api/                         # Typed client & API schemas
├── canons/                              # YAML brand rules (Acme Corp, Digital Lending, D2C Nutra)
└── docs/                                # Architecture decision records (ADRs) & documentation
```

---

## 📜 Documentation Links

* [**Architecture Diagram PDF**](./CanonGate_Architecture_Diagram.pdf)
* [**Pitch Deck PDF**](./CanonGate_Pitch_Deck.pdf)
* [**Architecture Decision Records (ADRs)**](./docs/adr/)
* [**AI Agent Development Guide**](./AGENTS.md)
* [**Feature Matrix & Gap Analysis**](./gap_analysis.md)
