# ADR 0004: Deterministic Tier 1 + Tier 2 + Constrained Tier 3 Execution Order

## Status
Accepted

## Context
Brand compliance platforms often face a trade-off between deterministic rigor and semantic flexibility:
- Relying exclusively on Large Language Models (LLMs) leads to non-deterministic compliance verdicts, slow evaluation times (>2 seconds per node), expensive API overhead, and hallucinations.
- Relying exclusively on naive keyword matching fails to capture mathematical claim arithmetic (e.g. drip pricing, APR compounding, discount bounds) and subtle semantic claim contradictions.

Regulatory bodies (ASCI, RBI, CCPA, FTC) require deterministic, auditable evidence for pre-publication gatekeeping.

## Decision
We implemented a **3-tiered execution hierarchy** governed by Angelopoulos et al. Conformal Risk Control:

### 1. Tier 1 — Purely Deterministic (Sub-millisecond)
Executes pure algorithmic and mathematical proofs without external network calls or stochastic models:
- `terminology.banned`: Regex-based term substitution with exact character offset tracking.
- `visual.palette_drift`: Sharma-Wu-Dalal (2005) CIEDE2000 ΔE00 color drift on flat banner regions.
- `accessibility.contrast`: W3C WCAG 2.1 relative luminance and Otsu foreground/background segmentation.
- `legibility.placement`: ASCI 26px / 1080p proportional disclaimer height rule.
- `unicode.confusable`: UTS #39 mixed-script spoofing and zero-width homoglyph detection.
- `security.hidden_text`: OWASP LLM01 defense against micro-font (<4pt), white-on-white, and CSS-hidden prompt injection.
- `visual.subordination`: Center-surround DoG (Difference of Gaussians) saliency verification.
- `c2pa.inbound`: Cryptographic C2PA manifest provenance validation.

### 2. Tier 2 — Symbolic & Calibrated SMT/NLI (10ms - 400ms)
Executes formal symbolic reasoning and guarded semantic alignment:
- `claim_algebra`: Z3 SMT solver (`z3.Real`) proving arithmetic equality, APR caps, and drip pricing fee structures. Returns formal counterexamples on SAT violations or UNSAT on mathematical validity.
- `claim_slot_nli`: Slot-based Natural Language Inference with strict 400ms timeout guards and calibrated threshold routing (0.45 - 0.85).

### 3. Tier 3 — Constrained Generative Linearization
Applied only for unstructured multimodal document flattening (e.g. complex nested tables in PDF/DOCX) via the Guarded LLM Table De-Normalizer. Requires Guard 1 verbatim text grounding to guarantee zero hallucinations before injecting text nodes into the AST.

### Conformal Risk Control
The platform calibrates semantic and visual finding confidence thresholds via distribution-free Conformal Risk Control. An interactive α slider (0.01 - 0.25) allows compliance officers to formally bound the maximum expected False Negative Rate (FNR) across governance scans.

## Consequences
- **Positive**: 90%+ of checks execute deterministically in sub-millisecond times, enabling real-time streaming feedback in the UI.
- **Positive**: Arithmetic disclosures (pricing, interest rates) have formal mathematical proof backing (Z3) rather than heuristic approximations.
- **Positive**: Conformal calibration provides statistical error bounds on semantic findings.
- **Negative**: Checks require explicit categorization and adherence to the tier latency contract.

## Alternatives Considered
- *All-in LLM Prompting*: Rejected because LLMs cannot be mathematically verified, vary across invocations, and violate legal reproducibility requirements.
- *Pure Regex Engine*: Rejected because regex cannot verify multi-currency arithmetic, date inequalities, or semantic synonym drift.
