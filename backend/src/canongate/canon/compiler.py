"""Pipeline A: Grounded Canon Compiler with Anti-Loss Guards 1 & 2 (`canon/compiler.py`).

Compiles raw brand books, RBI Key Fact Statements (KFS), and style guides
(`.pdf`, `.docx`, `.html`, `.md`, `.txt`) into a signed, immutable `Canon`
behind two deterministic anti-loss guards:

1. **Guard 1 — Value-Anchor Coverage Audit (`audit_anchor_coverage`):**
   Extracts every numeric value, percentage (`0%`, `27%`), currency amount
   (`₹50,000`, `Rs. 10 Lakh`, `$100`), ISO/quarter date (`Q3 2025`, `2026-09-30`),
   and restrictive qualifier clause (`under ...`, `up to ...`, `only ...`,
   `within ...`, `as of ...`, `valid until ...`) from source sentence $S$.
   Enforces `|Anchors(JSON)| / |Anchors(S)| == 1.0` by automatically injecting
   any uncaptured anchor or restrictive clause into `FactClaim.conditions`
   so LLM extraction can never silently drop a legal qualifier.

2. **Guard 2 — Verbatim Character-Interval Grounding (`ground_char_interval`):**
   Following `google/langextract`, maps every candidate rule's `source_text`
   to its exact `Span(start, end)` in the source document (`doc_text[start:end]`).
   Ungrounded/hallucinated rules that do not match verbatim source text return
   `None` and are rejected before Canon assembly.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from canongate.domain.ast import ContentAST, NodeKind, TextNode
from canongate.domain.canon import Canon, ColorToken, FactClaim, TermRule
from canongate.domain.finding import Span
from canongate.parsers.bundle import BundleInput, parse_bundle
from canongate.parsers.llm_table import MultiProviderJsonLLM, create_llm_canon_extractor

logger = logging.getLogger(__name__)

# Value anchors: percentages, currency + numbers, standalone numbers, quarters, ISO dates
_ANCHOR_RE = re.compile(
    r"(?:"
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\bQ[1-4]\s+\d{4}\b|"
    r"(?:₹|Rs\.?\s*|\$)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|lakhs|cr|crore|crores|k|m))?\b|"
    r"\b\d[\d,]*(?:\.\d+)?\s*%|"
    r"\b\d[\d,]*(?:\.\d+)?\b"
    r")",
    re.IGNORECASE,
)

# Restrictive qualifier clauses that must be preserved in FactClaim.conditions
_QUALIFIER_RE = re.compile(
    r"\b(?:only\s+(?:for|on|when|if)|under|up\s+to|within|as\s+of|valid\s+(?:until|till)|"
    r"subject\s+to|applicable\s+on)\s+(?:,(?=\d)|[^.;,\n|])+",
    re.IGNORECASE,
)

_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# Deterministic patterns for zero-LLM offline brand book compilation
_BANNED_RULE_RE = re.compile(
    r"""(?:never\s+use|avoid|ban(?:ned)?|do\s+not\s+use)\s+(?:['"])([^'"]+)(?:['"])\s*"""
    r"""(?:[,;—\-]+\s*)?(?:use|prefer|replace\s+with)\s+(?:['"])([^'"]+)(?:['"])""",
    re.IGNORECASE,
)
_HEX_TOKEN_RE = re.compile(r"(?:([A-Za-z][A-Za-z0-9 _\-]{1,32})\s*[:\-–]\s*)?(#[0-9A-Fa-f]{6})\b")


@dataclass(frozen=True, slots=True)
class AnchorAuditResult:
    """Result of Guard 1 Value-Anchor Coverage Audit on a single rule extraction."""

    source_anchors: tuple[str, ...]
    captured_anchors: tuple[str, ...]
    recovered_conditions: tuple[str, ...]

    @property
    def raw_recall(self) -> float:
        if not self.source_anchors:
            return 1.0
        return len(self.captured_anchors) / len(self.source_anchors)

    @property
    def effective_recall(self) -> float:
        """Recall after Guard 1 injects any missing anchors into `conditions`."""
        return 1.0


@dataclass(frozen=True, slots=True)
class GroundedRuleRecord:
    """Provenance record pairing a compiled Canon rule with its Guard 1 & 2 evidence."""

    rule_id: str
    rule_kind: str  # "term" | "color" | "fact"
    char_interval: Span
    source_text: str
    anchor_audit: AnchorAuditResult | None = None


def extract_value_anchors(text: str) -> tuple[str, ...]:
    """Extract all numeric, currency, percentage, and date anchors from `text`."""
    seen: list[str] = []
    for m in _ANCHOR_RE.finditer(text):
        tok = re.sub(r"\s+", " ", m.group(0).strip())
        if tok and tok not in seen:
            seen.append(tok)
    return tuple(seen)


def extract_restrictive_qualifiers(text: str) -> tuple[str, ...]:
    """Extract restrictive qualifier phrases (`under Rs 50,000`, `as of Q3 2025`, etc.)."""
    qualifiers: list[str] = []
    for m in _QUALIFIER_RE.finditer(text):
        q = re.sub(r"\s+", " ", m.group(0).strip())
        if q and q not in qualifiers:
            qualifiers.append(q)
    return tuple(qualifiers)


def ground_char_interval(source_doc: str, snippet: str) -> Span | None:
    """Guard 2: Locate the exact verbatim `Span(start, end)` of `snippet` in `source_doc`.

    Returns `None` if `snippet` is empty or cannot be grounded verbatim in `source_doc`.
    """
    cleaned = snippet.strip()
    if not cleaned or not source_doc:
        return None

    idx = source_doc.find(cleaned)
    if idx != -1:
        return Span(start=idx, end=idx + len(cleaned))

    # Whitespace-insensitive fallback that still maps to exact source_doc indices
    tokens = [re.escape(tok) for tok in cleaned.split() if tok]
    if not tokens:
        return None
    flex_pat = re.compile(r"\s+".join(tokens))
    match = flex_pat.search(source_doc)
    if match is None:
        return None
    return Span(start=match.start(), end=match.end())


def audit_and_repair_fact_claim(
    fact: FactClaim,
    source_sentence: str,
) -> tuple[FactClaim, AnchorAuditResult]:
    """Guard 1: Verify 100% value-anchor recall and inject any dropped conditions."""
    src_anchors = extract_value_anchors(source_sentence)
    combined_rule_text = " ".join([fact.text, *fact.conditions, fact.valid_until or ""])
    combined_norm = combined_rule_text.lower()

    captured: list[str] = []
    missing_anchors: list[str] = []
    for anchor in src_anchors:
        if anchor.lower() in combined_norm:
            captured.append(anchor)
        else:
            missing_anchors.append(anchor)

    updated_conditions = list(fact.conditions)
    recovered: list[str] = []

    # 1. Check restrictive qualifier phrases in the source sentence
    for qual in extract_restrictive_qualifiers(source_sentence):
        if qual.lower() not in combined_norm and qual not in updated_conditions:
            updated_conditions.append(qual)
            recovered.append(qual)
            combined_norm = f"{combined_norm} {qual.lower()}"

    # 2. Ensure any remaining uncaptured numeric/currency/date anchor is preserved
    for anchor in missing_anchors:
        if anchor.lower() not in combined_norm:
            clause = f"anchor: {anchor}"
            updated_conditions.append(clause)
            recovered.append(clause)

    date_match = _DATE_RE.search(source_sentence)
    valid_until = fact.valid_until or (date_match.group(1) if date_match else None)

    repaired_fact = FactClaim(
        id=fact.id,
        text=fact.text,
        conditions=updated_conditions,
        valid_until=valid_until,
    )
    audit = AnchorAuditResult(
        source_anchors=src_anchors,
        captured_anchors=tuple(captured),
        recovered_conditions=tuple(recovered),
    )
    return repaired_fact, audit


class CanonCompiler:
    """Pipeline A compiler: converts brand documents/ASTs into a grounded `Canon`."""

    __slots__ = ("_llm_extractor",)

    def __init__(
        self,
        llm_extractor: Callable[[str], dict[str, Any]] | None = None,
        *,
        llm_client: MultiProviderJsonLLM | None = None,
    ) -> None:
        self._llm_extractor = llm_extractor or create_llm_canon_extractor(llm_client)

    def compile(
        self,
        *inputs: BundleInput,
        canon_id: str = "compiled-canon",
        version: str = "1.0",
        ast: ContentAST | None = None,
    ) -> tuple[Canon, tuple[GroundedRuleRecord, ...]]:
        """Compile input documents or a `ContentAST` into `(Canon, provenance_records)`."""
        bundle_ast = ast if ast is not None else parse_bundle(*inputs)
        text_nodes = [n for n in bundle_ast.of_kind(NodeKind.TEXT) if isinstance(n, TextNode)]
        full_doc = "\n\n".join(n.text for n in text_nodes)

        raw_candidates = (
            self._llm_extractor(full_doc)
            if self._llm_extractor is not None
            else self._deterministic_extract(text_nodes)
        )

        terms: list[TermRule] = []
        colors: list[ColorToken] = []
        facts: list[FactClaim] = []
        provenance: list[GroundedRuleRecord] = []

        # 1. Ground and validate Terminology rules
        for idx, t_raw in enumerate(raw_candidates.get("terminology", ())):
            src_txt = str(t_raw.get("source_text") or t_raw.get("pattern_text") or "").strip()
            span = ground_char_interval(full_doc, src_txt)
            if span is None:
                logger.warning("Guard 2 rejected ungrounded TermRule: %r", t_raw)
                continue
            rule = TermRule(
                id=str(t_raw.get("id") or f"term-{idx + 1}"),
                pattern_text=str(t_raw["pattern_text"]),
                preferred=str(t_raw["preferred"]),
                severity=int(t_raw.get("severity", 60)),
                note=span.slice(full_doc),
            )
            terms.append(rule)
            provenance.append(
                GroundedRuleRecord(
                    rule_id=rule.id,
                    rule_kind="term",
                    char_interval=span,
                    source_text=span.slice(full_doc),
                )
            )

        # 2. Ground and validate Palette ColorTokens
        for idx, c_raw in enumerate(raw_candidates.get("palette", ())):
            hex_code = str(c_raw.get("hex", "")).strip()
            src_txt = str(c_raw.get("source_text") or hex_code).strip()
            span = ground_char_interval(full_doc, src_txt)
            if span is None:
                logger.warning("Guard 2 rejected ungrounded ColorToken: %r", c_raw)
                continue
            token = ColorToken(
                id=str(c_raw.get("id") or f"color-{idx + 1}"),
                hex=hex_code,
                name=str(c_raw.get("name", "")).strip(),
                max_delta_e=float(c_raw.get("max_delta_e", 3.0)),
            )
            colors.append(token)
            provenance.append(
                GroundedRuleRecord(
                    rule_id=token.id,
                    rule_kind="color",
                    char_interval=span,
                    source_text=span.slice(full_doc),
                )
            )

        # 3. Ground and repair FactClaims via Guard 2 + Guard 1
        for idx, f_raw in enumerate(raw_candidates.get("facts", ())):
            src_txt = str(f_raw.get("source_text") or f_raw.get("text") or "").strip()
            span = ground_char_interval(full_doc, src_txt)
            if span is None:
                logger.warning("Guard 2 rejected ungrounded FactClaim: %r", f_raw)
                continue
            grounded_sentence = span.slice(full_doc)
            initial_fact = FactClaim(
                id=str(f_raw.get("id") or f"fact-{idx + 1}"),
                text=str(f_raw.get("text") or grounded_sentence).strip(),
                conditions=[str(c) for c in f_raw.get("conditions", ())],
                valid_until=f_raw.get("valid_until"),
            )
            repaired_fact, audit = audit_and_repair_fact_claim(initial_fact, grounded_sentence)
            facts.append(repaired_fact)
            provenance.append(
                GroundedRuleRecord(
                    rule_id=repaired_fact.id,
                    rule_kind="fact",
                    char_interval=span,
                    source_text=grounded_sentence,
                    anchor_audit=audit,
                )
            )

        canon = Canon(
            id=canon_id,
            version=version,
            terminology=tuple(terms),
            palette=tuple(colors),
            facts=tuple(facts),
        )
        return canon, tuple(provenance)

    def __call__(
        self,
        *inputs: BundleInput,
        canon_id: str = "compiled-canon",
        version: str = "1.0",
    ) -> Canon:
        canon, _ = self.compile(*inputs, canon_id=canon_id, version=version)
        return canon

    @staticmethod
    def _deterministic_extract(text_nodes: Sequence[TextNode]) -> dict[str, list[dict[str, Any]]]:
        """Zero-LLM deterministic rule extractor for brand books and linearized KFS tables."""
        terminology: list[dict[str, Any]] = []
        palette: list[dict[str, Any]] = []
        facts: list[dict[str, Any]] = []
        seen_hex: set[str] = set()

        for node in text_nodes:
            block = node.text

            # 1. Extract banned terminology patterns
            for m in _BANNED_RULE_RE.finditer(block):
                terminology.append(
                    {
                        "pattern_text": m.group(1).strip(),
                        "preferred": m.group(2).strip(),
                        "severity": 60,
                        "source_text": m.group(0),
                    }
                )

            # 2. Extract hex colour tokens
            for m in _HEX_TOKEN_RE.finditer(block):
                name_raw = (m.group(1) or "").strip()
                hex_val = m.group(2).upper()
                if hex_val not in seen_hex:
                    seen_hex.add(hex_val)
                    palette.append(
                        {
                            "hex": hex_val,
                            "name": name_raw or f"Color {len(palette) + 1}",
                            "source_text": m.group(0),
                        }
                    )

            # 3. Extract factual / tabular claims containing value anchors
            if "/table[" in node.path or (
                extract_value_anchors(block)
                and not _BANNED_RULE_RE.search(block)
                and not _HEX_TOKEN_RE.search(block)
            ):
                facts.append(
                    {
                        "text": block,
                        "conditions": list(extract_restrictive_qualifiers(block)),
                        "source_text": block,
                    }
                )

        return {
            "terminology": terminology,
            "palette": palette,
            "facts": facts,
        }


def compile_canon(
    *inputs: BundleInput,
    canon_id: str = "compiled-canon",
    version: str = "1.0",
    llm_extractor: Callable[[str], dict[str, Any]] | None = None,
    llm_client: MultiProviderJsonLLM | None = None,
) -> tuple[Canon, tuple[GroundedRuleRecord, ...]]:
    """Convenience function to compile inputs into `(Canon, provenance_records)`."""
    compiler = CanonCompiler(llm_extractor=llm_extractor, llm_client=llm_client)
    return compiler.compile(*inputs, canon_id=canon_id, version=version)
