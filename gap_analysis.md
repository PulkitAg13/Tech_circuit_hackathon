# Walking Skeleton vs Full Feature Set — Gap Analysis

## What "Walking Skeleton" Means

A walking skeleton is **the thinnest possible slice that runs through every layer end-to-end**. It's not a prototype or a stub — it's real code with real data flowing through it. The value is that **all the hard integration problems are solved once** (streaming, auth, state machine, audit chain, char-offset mapping) so your 4 teammates can work in parallel without stepping on each other.

Think of it as: the plumbing and wiring of the house is done, but you only have 1 lightbulb installed to prove electricity works.

---

## What's IN the Skeleton vs What's MISSING

### Backend Checks (the main growth area)

| Check | Skeleton | Full Feature | Status |
|-------|----------|-------------|--------|
| `terminology.banned` — regex banned words | ✅ Built, working | ✅ Done | **DONE** |
| `visual.palette_drift` — CIEDE2000 colour distance | ✅ Built, wired & tested | Sharma-Wu-Dalal (2005) CIEDE2000 ΔE00 drift on flat banner regions & tokens | **DONE** |
| `claim_fact` / `claim_slot_nli` — NLI-based fact checking | ✅ Built, wired & tested | Tier 2 semantic-category value alignment, `substantiation_level` (ASCI in-vitro vs clinical), 400ms timeout guard, & calibrated 0.45–0.85 Warning routing | **DONE** |
| `claim_algebra` — SMT solver proofs | ✅ Built, wired & tested | Tier 1.5 Z3 SMT solver (`z3.Real`) + interval fallback, ₹ Lakh/Crore caps, date inequalities, & FirstCry (PIB 2171807) single/cross-node Drip Pricing | **DONE** |
| `accessibility.contrast` — WCAG AA/AAA | ✅ Built, wired & tested | W3C WCAG 2.1 relative luminance, Otsu text fg/bg segmentation, CIELab suggested hex | **DONE** |
| `legibility.placement` — ASCI 26px rule | ✅ Built, wired & tested | ASCI 26px / 1080p proportional disclaimer height & single/cross-node (`run_bundle`) CCPA Clause 11 Hindi/English parity | **DONE** |
| `visual.subordination` — saliency check | ✅ Built, wired & tested | Multi-scale DoG center-surround saliency (<25% floor) | **DONE** |
| `unicode.confusable` — TR39 homoglyphs | ✅ Built, wired & tested | UTS #39 mixed-script spoof detection & zero-width character detection | **DONE** |
| `c2pa.inbound` — provenance verification | ✅ Built, wired & tested | c2pa manifest validator & AI provenance blocker | **DONE** |
| `security.hidden_text` — hidden prompt injection | ✅ Built, wired & tested | OWASP LLM01 micro-font (<4pt), white-on-white, & CSS-hidden prompt injection defense | **DONE** |

### Parsers

| Parser | Skeleton | Full Feature | Status |
|--------|----------|-------------|--------|
| Plain text / Markdown → TextNodes | ✅ Paragraph splitting | Proper heading/list/image extraction | **DONE** |
| Image → ImageNode | ✅ Built, wired & tested | PIL metadata + markdown/direct ImageNode parsing | **DONE** |
| DOCX parser | ✅ Built, wired & tested | `python-docx` reading order, `TableGrid` linearization, embedded image extraction | **DONE** |
| PDF parser | ✅ Built, wired & tested | `pdfplumber` / `pypdf` tables, micro-font & white-on-white text isolation | **DONE** |
| HTML parser | ✅ Built, wired & tested | `BeautifulSoup` script/style strip, CSS-hidden text isolation, table linearization | **DONE** |
| Banner / Multimodal Bundle parser | ✅ Built, wired & tested | Morphological text-box detection, OCR text node injection, bundle dispatcher | **DONE** |
| Guarded LLM Table De-Normalizer | ✅ Built, wired & tested | Multi-provider (Gemini, OpenAI/Groq, Ollama) Guard 1 zero-hallucination linearizer | **DONE** |

### Canon System

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| YAML loader | ✅ Working | ✅ Done | **DONE** |
| Canon compiler (Pipeline A) | ✅ Built, wired & tested | Guard 1 Value-Anchor Audit + Guard 2 Exact/LCS Fuzzy Grounding + Guard 3 Round-Trip NLI (≥0.90) + `POST /api/canons/compile` | **DONE** |
| Canon lint (Contradiction & Overlap Audit) | ✅ Built, wired & tested | Rule contradiction, overlap, & ungrounded pattern linting (wired to `GET /api/canons/{id}/lint`) | **DONE** |
| Canon versioning + impact sim | ✅ Built, wired & tested | Closed-loop Friction → Canon v1.1 PR simulation across `TermRule`, `ColorToken`, & `FactClaim` + Canon Governance Studio UI | **DONE** |
| Starter Canons | ✅ Built, wired & tested | RBI 2025 KFS Lending Canon & ASCI/CCPA D2C Nutra Canon | **DONE** |

### Engine

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| Async runner + `as_completed` streaming | ✅ Working | ✅ Done | **DONE** |
| `to_thread` for sync checks | ✅ Working | ✅ Done | **DONE** |
| In-memory LRU cache | ✅ Working | ✅ Done | **DONE** |
| Cross-node bundle runner (`run_bundle`) | ✅ Built, wired & tested | Full-document AST evaluation for stacked tax drip pricing & cross-script parity | **DONE** |
| Fault isolation (timeout + anti-cache-poisoning) | ✅ Built, wired & tested | asyncio.wait_for per-check timeout + immutable tuple cache | **DONE** |
| Deterministic sort of findings | ✅ Built, wired & tested | Sort by (node_order, locator.key, check_id, id) | **DONE** |
| Incremental re-check (only changed nodes) | ✅ Built, wired & tested | Content-hash cache invalidation & selective node dispatch | **DONE** |
| Deterministic replay manifest | ✅ Built, wired & tested | ast_hash + registered checks + alpha threshold (`GET /api/submissions/{id}/replay-manifest`) | **DONE** |
| Conformal risk control (α slider) | ✅ Built, wired & tested | Angelopoulos et al. distribution-free calibrated cutoff (`engine/conformal.py` + UI slider) | **DONE** |
| Mutation-tested gate | ✅ Built, wired & tested | Adversarial & property gate across 5 operators (`tests/engine/test_mutations.py`) | **DONE** |

### Workflow & Audit

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| State machine (5 states, 7 transitions) | ✅ Working | Role-gated transitions + Blocker gate (409 on APPROVE/PUBLISH with open blockers) | **DONE** |
| Role-gated transitions | ✅ Working | ✅ Done | **DONE** |
| Finding resolution (accept/dismiss/override) | ✅ Working | ✅ Done | **DONE** |
| SHA-256 hash-chained audit log | ✅ Working | Unbroken hash-chain verification with submission_id | **DONE** |
| Chain verification | ✅ Working | ✅ Done | **DONE** |
| Submission versioning (immutable revisions) | ✅ Built, wired & tested | Each save → new `SubmissionVersionRow` revision with change notes (`/versions`) | **DONE** |
| Merkle transparency log (RFC 9162) | ✅ Built, wired & tested | O(log n) proofs, Ed25519 tree heads (STH API), memoized MerkleTree | **DONE** |
| C2PA outbound (embed review in approved PNG) | ✅ Built, wired & tested | `cryptography.x509` ECDSA P-256 (`ES256`) certificate generator + `c2pa-python` Builder & `.c2pa.json` cryptographic sidecar | **DONE** |
| Standalone verifier CLI | ✅ Built, wired & tested | `canongate verify cert.json` offline cryptographic governance verifier (`cli.py`) | **DONE** |
| Override requires reason text | ✅ Built, wired & tested | Cognitive forcing function requiring >=3 chars justification (`resolution_reason`) | **DONE** |
| Friction analytics (override rate per rule) | ✅ Built, wired & tested | Empirical Bayes Beta-Binomial + Krippendorff's α API | **DONE** |

### Frontend

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| Login / Register with role selection | ✅ Working | ✅ Done | **DONE** |
| Submission list (dashboard) | ✅ Working | ✅ Done | **DONE** |
| Create submission (textarea + parser integration) | ✅ Working | Tiptap rich editor + multimodal file attachment bundle upload + Canon Admin suite | **DONE** |
| SSE scan with live finding count | ✅ Working | ✅ Done | **DONE** |
| Finding cards with verdict/severity/tier | ✅ Working | ✅ Done | **DONE** |
| Accept/Dismiss/Override buttons | ✅ Working | ✅ Done | **DONE** |
| Workflow action buttons | ✅ Working | ✅ Done | **DONE** |
| Audit trail modal with hash chain | ✅ Working | ✅ Done | **DONE** |
| Dark glassmorphism design | ✅ Working | ✅ Done | **DONE** |
| **Tiptap editor with inline highlights** | ✅ Built, wired & tested | ProseMirror 1-indexed & UTF-16 surrogate highlights mounted | **DONE** |
| **Image BBox overlay** | ✅ Built, wired & tested | Interactive SVG `BannerBBoxOverlay` showing pixel BBox locators on campaign banners | **DONE** |
| **α slider (conformal risk)** | ✅ Built, wired & tested | Interactive threshold control (0.01 - 0.25) wired to SSE scan & calibrated filtering | **DONE** |
| **Context Trace badge details** | ✅ Built, wired & tested | Full: tier emoji, latency ms, & model SHA metadata | **DONE** |
| Auto-generated TypeScript types from OpenAPI | ✅ Built, wired & tested | `openapi-typescript` + `npm run generate:api` + `src/api/schema.d.ts` | **DONE** |
| TanStack Router (file-based) | ❌ | Using react-router-dom instead | **DEFERRED** |
| TanStack Query (caching/refetch) | ✅ Built, wired & tested | `@tanstack/react-query` v5 for server state, mutations & cache invalidation | **DONE** |
| Evidence renderers (one per kind) | ✅ Built, wired & tested | All 10 Discriminated Evidence UI components with CSS styling | **DONE** |
| Playwright E2E test | ✅ Built, wired & tested | `tests/golden-path.spec.ts` real backend+frontend journey (`npm run test:e2e`) | **DONE** |

### Infrastructure

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| Makefile | ✅ Working | ✅ Done | **DONE** |
| uv lockfile | ✅ Working | ✅ Done | **DONE** |
| AGENTS.md | ✅ Working | ✅ Done | **DONE** |
| import-linter contracts | ✅ Configured | 3 architectural boundaries enforced | **DONE** |
| docker-compose.yml | ✅ Built, wired & tested | `api` + `frontend` container orchestration with SQLite volume | **DONE** |
| CI pipeline (GitHub Actions) | ✅ Built, wired & tested | `.github/workflows/ci.yml` (ruff, pytest, import-linter, tsc, vite build) | **DONE** |
| ADR documents | ✅ Documented | `docs/adr/0001-0005.md` (architecture, boundaries, SQLite, tiered execution, audit) | **DONE** |

---

## Summary Scorecard

| Category | Done | Partial | Missing | Total |
|----------|------|---------|---------|-------|
| Backend Checks | 10 | 0 | 0 | 10 |
| Parsers | 7 | 0 | 0 | 7 |
| Canon System | 5 | 0 | 0 | 5 |
| Engine | 10 | 0 | 0 | 10 |
| Workflow & Audit | 11 | 0 | 0 | 11 |
| Frontend | 17 | 0 | 1 (deferred) | 18 |
| Infrastructure | 7 | 0 | 0 | 7 |
| **TOTAL** | **67** | **0** | **1** | **68** |

**100% of Actionable Implementation Gaps Closed (67/68 features complete, 1 deferred: TanStack Router).** All 10 governance checks (spanning computer vision, SMT arithmetic proofs, NLI slot alignment, WCAG contrast, UTS #39 homoglyphs, and OWASP hidden prompt injection), multimodal parsers (DOCX, PDF, HTML, banner image, multi-provider Guarded LLM table de-normalization, base64 bundle attachments), cross-node bundle engine (`run_bundle`), Pipeline A CanonCompiler with Guards 1, 2 & 3 (Value-Anchor Coverage, Verbatim Span Grounding, and Bidirectional Round-Trip NLI), Canon v1.1 PR generator for TermRules and FactClaims, real X.509 v3 ES256 C2PA outbound asset signing, surgical 1-click Accept replacements with span-shifting, standalone offline CLI verifier (`canongate verify`), Conformal Risk Control with interactive α slider, immutable revision history (`SubmissionVersionRow`), cognitive forcing functions, SVG pixel BBox overlays on banner ads, `docker-compose.yml`, GitHub Actions CI pipeline, 10 rich frontend evidence renderers, automated OpenAPI TypeScript generation (`npm run generate:api`), TanStack Query server-state management, Playwright golden-path E2E testing (`npm run test:e2e`), and 5 comprehensive ADR records are fully operational and validated.
