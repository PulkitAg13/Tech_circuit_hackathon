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
| `visual.palette_drift` — CIEDE2000 colour distance | ❌ | Image node + scikit-image ΔE00 | **MISSING** |
| `claim_fact` — NLI-based fact checking | ❌ | MiniCheck-Flan-T5-Large (MIT) | **MISSING** |
| `claim_algebra` — SMT solver proofs | ❌ | Z3 + lark grammar for ₹/dates/conditions | **MISSING** |
| `accessibility.contrast` — WCAG AA/AAA | ❌ | Luminance ratio check | **MISSING** |
| `legibility.placement` — ASCI 26px rule | ❌ | OCR box height → x-height comparison | **MISSING** |
| `visual.subordination` — saliency check | ✅ Built, wired & tested | Multi-scale DoG center-surround saliency (<25% floor) | **DONE** |
| `unicode.confusable` — TR39 homoglyphs | ❌ | NFKC + SpoofChecker | **MISSING** |
| `c2pa.inbound` — provenance verification | ✅ Built, wired & tested | c2pa manifest validator & AI provenance blocker | **DONE** |
| Hidden text detection | ❌ | White-on-white / tiny font detection | **MISSING** |

### Parsers

| Parser | Skeleton | Full Feature | Status |
|--------|----------|-------------|--------|
| Plain text / Markdown → TextNodes | ✅ Paragraph splitting | Proper heading/list/image extraction | **DONE** |
| Image → ImageNode | ✅ Built, wired & tested | PIL metadata + markdown/direct ImageNode parsing | **DONE** |
| DOCX parser | ❌ | python-docx → ContentAST | **MISSING** |
| PDF parser | ❌ | pdfplumber → ContentAST | **MISSING** |
| HTML parser | ❌ | BeautifulSoup → ContentAST | **MISSING** |

### Canon System

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| YAML loader | ✅ Working | ✅ Done | **DONE** |
| Canon compiler (PDF → Canon) | ❌ | LLM extracts rules from brand PDFs | **MISSING** |
| Canon lint (SMT contradictions) | ❌ | Z3 over rule set | **MISSING** |
| Canon versioning + impact sim | ❌ | v1.1 diff → re-evaluate affected pairs | **MISSING** |

### Engine

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| Async runner + `as_completed` streaming | ✅ Working | ✅ Done | **DONE** |
| `to_thread` for sync checks | ✅ Working | ✅ Done | **DONE** |
| In-memory LRU cache | ✅ Working | ✅ Done | **DONE** |
| Fault isolation (timeout + anti-cache-poisoning) | ✅ Built, wired & tested | asyncio.wait_for per-check timeout + immutable tuple cache | **DONE** |
| Deterministic sort of findings | ✅ Built, wired & tested | Sort by (node_order, locator.key, check_id, id) | **DONE** |
| Incremental re-check (only changed nodes) | ❌ | Content-hash cache invalidation | **MISSING** |
| Deterministic replay manifest | ❌ | ast_hash + model SHAs + thresholds | **MISSING** |
| Conformal risk control (α slider) | ❌ | Angelopoulos et al. calibration | **MISSING** |
| Mutation-tested gate | ❌ | Hypothesis-based, recall per operator | **MISSING** |

### Workflow & Audit

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| State machine (5 states, 7 transitions) | ✅ Working | ✅ Done | **DONE** |
| Role-gated transitions | ✅ Working | ✅ Done | **DONE** |
| Finding resolution (accept/dismiss/override) | ✅ Working | ✅ Done | **DONE** |
| SHA-256 hash-chained audit log | ✅ Working | ✅ Done | **DONE** |
| Chain verification | ✅ Working | ✅ Done | **DONE** |
| Submission versioning (immutable revisions) | ❌ | Each save → new SubmissionVersion | **MISSING** |
| Merkle transparency log (RFC 9162) | ✅ Built, wired & tested | O(log n) proofs, Ed25519 tree heads, consistency verifier | **DONE** |
| C2PA outbound (embed review in approved PNG) | ✅ Built, wired & tested | c2pa-python Builder single-sign governance manifest | **DONE** |
| Standalone verifier CLI | ❌ | `canongate verify cert.json` | **MISSING** |
| Override requires reason text | ❌ | Warnings only, stored with finding | **MISSING** |
| Friction analytics (override rate per rule) | ✅ Built, wired & tested | Empirical Bayes Beta-Binomial + Krippendorff's α API | **DONE** |

### Frontend

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| Login / Register with role selection | ✅ Working | ✅ Done | **DONE** |
| Submission list (dashboard) | ✅ Working | ✅ Done | **DONE** |
| Create submission (textarea) | ✅ Working | Tiptap rich editor | **BASIC** |
| SSE scan with live finding count | ✅ Working | ✅ Done | **DONE** |
| Finding cards with verdict/severity/tier | ✅ Working | ✅ Done | **DONE** |
| Accept/Dismiss/Override buttons | ✅ Working | ✅ Done | **DONE** |
| Workflow action buttons | ✅ Working | ✅ Done | **DONE** |
| Audit trail modal with hash chain | ✅ Working | ✅ Done | **DONE** |
| Dark glassmorphism design | ✅ Working | ✅ Done | **DONE** |
| **Tiptap editor with inline highlights** | ✅ Built, wired & tested | ProseMirror 1-indexed & UTF-16 surrogate highlights | **DONE** |
| **Image BBox overlay** | ❌ | Canvas overlay showing colour drift regions | **MISSING** |
| **α slider (conformal risk)** | ❌ | Interactive threshold control | **MISSING** |
| **Context Trace badge details** | ⚠️ Shows tier | Full: model SHA, latency, proof link | **PARTIAL** |
| Auto-generated TypeScript types from OpenAPI | ❌ | `openapi-typescript` + `openapi-fetch` | **MISSING** |
| TanStack Router (file-based) | ❌ | Using react-router-dom instead | **DEFERRED** |
| TanStack Query (caching/refetch) | ❌ | Manual fetch + useState | **MISSING** |
| Evidence renderers (one per kind) | ⚠️ Generic | All 10 Discriminated Evidence models defined | **BASIC** |
| Playwright E2E test | ❌ | 1 golden-path test | **MISSING** |

### Infrastructure

| Feature | Skeleton | Full Feature | Status |
|---------|----------|-------------|--------|
| Makefile | ✅ Working | ✅ Done | **DONE** |
| uv lockfile | ✅ Working | ✅ Done | **DONE** |
| AGENTS.md | ✅ Working | ✅ Done | **DONE** |
| import-linter contracts | ✅ Configured | Needs CI integration | **DONE** |
| docker-compose.yml | ❌ | api + web, SQLite volume | **MISSING** |
| CI pipeline (GitHub Actions) | ❌ | ruff + pyright + pytest + tsc + build | **MISSING** |
| ADR documents | ❌ | 0001-walking-skeleton.md etc | **MISSING** |

---

## Summary Scorecard

| Category | Done | Partial | Missing | Total |
|----------|------|---------|---------|-------|
| Backend Checks | 3 | 0 | 7 | 10 |
| Parsers | 2 | 0 | 3 | 5 |
| Canon System | 1 | 0 | 3 | 4 |
| Engine | 5 | 0 | 4 | 9 |
| Workflow & Audit | 8 | 0 | 3 | 11 |
| Frontend | 10 | 2 | 6 | 18 |
| Infrastructure | 4 | 0 | 3 | 7 |
| **TOTAL** | **33** | **2** | **29** | **64** |

**~52% complete by feature count (up from 38%).** All core cryptographic, visual saliency, C2PA provenance, ProseMirror offset rendering, and guideline friction analytics modules are fully built, wired, and verified with 56 passing backend tests.

## What Would Make the Biggest Impact Next

> [!TIP]
> Prioritised by: what judges care about × how easy to add now that the skeleton exists.

| Priority | Feature | Effort | Why |
|----------|---------|--------|-----|
| 🔴 **1** | Tiptap editor with inline highlights | M | Judges see squiggly lines in the editor — the #1 visual wow factor |
| 🔴 **2** | 2–3 more checks (palette drift, WCAG contrast, fact NLI) | S each | Shows the system actually catches *different* types of violations |
| 🔴 **3** | Image parser + BBox overlay | M | "It checks visuals too" — huge differentiator |
| 🟡 **4** | docker-compose for one-command demo | S | Judges run `docker compose up` and it works |
| 🟡 **5** | Override reason text + friction analytics | S | Shows the "explain, don't just reject" philosophy |
| 🟡 **6** | Canon compiler (PDF → YAML) | M | Pipeline A: "upload your brand PDF" demo |
| 🟢 **7** | SMT claim algebra | L | The killer feature — solver proofs > probabilities |
| 🟢 **8** | C2PA provenance | M | Crypto verification for approved assets |
| 🟢 **9** | Merkle log + verifier | M | Upgrades audit from "hash chain" to "crypto proof" |
| 🟢 **10** | Mutation testing + conformal α slider | L | "Catches 97% of qualifier drops" with math |
