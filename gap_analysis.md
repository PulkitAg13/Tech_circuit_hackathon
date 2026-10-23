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
| Incremental re-check (only changed nodes) | ❌ | Content-hash cache invalidation | **MISSING** |
| Deterministic replay manifest | ❌ | ast_hash + model SHAs + thresholds | **MISSING** |
| Conformal risk control (α slider) | ❌ | Angelopoulos et al. calibration | **MISSING** |
| Mutation-tested gate | ❌ | Hypothesis-based, recall per operator | **MISSING** |

### Workflow & Audit

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| State machine (5 states, 7 transitions) | ✅ Working | Role-gated transitions + Blocker gate (409 on APPROVE/PUBLISH with open blockers) | **DONE** |
| Role-gated transitions | ✅ Working | ✅ Done | **DONE** |
| Finding resolution (accept/dismiss/override) | ✅ Working | ✅ Done | **DONE** |
| SHA-256 hash-chained audit log | ✅ Working | Unbroken hash-chain verification with submission_id | **DONE** |
| Chain verification | ✅ Working | ✅ Done | **DONE** |
| Submission versioning (immutable revisions) | ❌ | Each save → new SubmissionVersion | **MISSING** |
| Merkle transparency log (RFC 9162) | ✅ Built, wired & tested | O(log n) proofs, Ed25519 tree heads (STH API), memoized MerkleTree | **DONE** |
| C2PA outbound (embed review in approved PNG) | ✅ Built, wired & tested | `cryptography.x509` ECDSA P-256 (`ES256`) certificate generator + `c2pa-python` Builder & `.c2pa.json` cryptographic sidecar | **DONE** |
| Standalone verifier CLI | ❌ | `canongate verify cert.json` | **MISSING** |
| Override requires reason text | ❌ | Warnings only, stored with finding | **MISSING** |
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
| **Image BBox overlay** | ❌ | Canvas overlay showing colour drift / OCR regions | **MISSING** |
| **α slider (conformal risk)** | ❌ | Interactive threshold control | **MISSING** |
| **Context Trace badge details** | ✅ Built, wired & tested | Full: tier emoji, latency ms, & model SHA metadata | **DONE** |
| Auto-generated TypeScript types from OpenAPI | ❌ | `openapi-typescript` + `openapi-fetch` | **MISSING** |
| TanStack Router (file-based) | ❌ | Using react-router-dom instead | **DEFERRED** |
| TanStack Query (caching/refetch) | ❌ | Manual fetch + useState | **MISSING** |
| Evidence renderers (one per kind) | ✅ Built, wired & tested | All 10 Discriminated Evidence UI components with CSS styling | **DONE** |
| Playwright E2E test | ❌ | 1 golden-path test | **MISSING** |

### Infrastructure

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| Makefile | ✅ Working | ✅ Done | **DONE** |
| uv lockfile | ✅ Working | ✅ Done | **DONE** |
| AGENTS.md | ✅ Working | ✅ Done | **DONE** |
| import-linter contracts | ✅ Configured | 3 architectural boundaries enforced | **DONE** |
| docker-compose.yml | ❌ | api + web, SQLite volume | **MISSING** |
| CI pipeline (GitHub Actions) | ❌ | ruff + pyright + pytest + tsc + build | **MISSING** |
| ADR documents | ❌ | 0001-walking-skeleton.md etc | **MISSING** |

---

## Summary Scorecard

| Category | Done | Partial | Missing | Total |
|----------|------|---------|---------|-------|
| Backend Checks | 10 | 0 | 0 | 10 |
| Parsers | 7 | 0 | 0 | 7 |
| Canon System | 5 | 0 | 0 | 5 |
| Engine | 6 | 0 | 4 | 10 |
| Workflow & Audit | 8 | 0 | 3 | 11 |
| Frontend | 12 | 0 | 6 | 18 |
| Infrastructure | 4 | 0 | 3 | 7 |
| **TOTAL** | **52** | **0** | **16** | **68** |

**~76.5% complete by feature count.** All 10 governance checks (spanning computer vision, SMT arithmetic proofs, NLI slot alignment, WCAG contrast, UTS #39 homoglyphs, and OWASP hidden prompt injection), multimodal parsers (DOCX, PDF, HTML, banner image, multi-provider Guarded LLM table de-normalization, base64 bundle attachments), cross-node bundle engine (`run_bundle`), Pipeline A CanonCompiler with Guards 1, 2 & 3 (Value-Anchor Coverage, Verbatim Span Grounding, and Bidirectional Round-Trip NLI), Canon v1.1 PR generator for TermRules and FactClaims, real X.509 v3 ES256 C2PA outbound asset signing, surgical 1-click Accept replacements with span-shifting, and 10 rich frontend evidence renderers are fully wired, operational, and validated with **76 passing tests**.

## Remaining Impact Opportunities

| Priority | Feature | Effort | Why |
|----------|---------|--------|-----|
| 🔴 **1** | docker-compose for one-command demo | S | Judges run `docker compose up` and the complete stack boots instantly |
| 🔴 **2** | Standalone verifier CLI | S | `canongate verify audit_manifest.json` demonstrates tamperproof verification offline |
| 🟡 **3** | Image BBox canvas overlay | M | Visual bounding box highlights for palette drift and contrast violations |
| 🟡 **4** | CI Pipeline (GitHub Actions) | S | Continuous verification of `pytest`, `ruff`, `import-linter`, and `tsc` on push |
| 🟢 **5** | Conformal risk control (α slider) | M | Mathematical guarantees bounding false discovery rates |
