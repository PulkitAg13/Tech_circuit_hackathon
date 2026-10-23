"""Tier 1.5 Check: SMT / Algebraic & Temporal Constraint Verifier (`claim.algebra`).

Verifies mathematical, currency-cap (Indian numbering: Lakh, Crore), temporal
(`valid_until`), and stacked-tax discount equations in `TextNode`s:
1. **Upper-Bound Cap Breach:** Proves $\\exists x \\in (C_{\\text{max}}, D_{\\text{max}}]:
   P_{\\text{draft}}(x) \\land \\neg P_{\\text{canon}}(x)$ when a draft claims a higher
   currency/numeric cap than permitted by `FactClaim` conditions (e.g., draft
   claims `"up to ₹1,00,000"` when KFS Canon states `"under Rs 50,000"`).
2. **Temporal Expiry Breach:** Proves `draft_valid_until > canon.valid_until`
   on ISO date claims (`YYYY-MM-DD`).
3. **Stacked Tax / Net Discount Contradiction (FirstCry CCPA PIB 2171807):**
   Proves $1 - (1 - d)(1 + g) < d$ when a draft claims `"Flat d% Off (Inclusive
   of all taxes)"` while adding `"+ g% GST applies"` on the discounted price.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from canongate.domain.ast import Node, NodeKind, TextNode
from canongate.domain.canon import Canon, FactClaim, Rule
from canongate.domain.finding import (
    AlgebraicProofEvidence,
    Finding,
    Replace,
    Span,
    Suggestion,
    Tier,
    Trace,
)
from canongate.engine.check import Check

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "on",
        "in",
        "for",
        "of",
        "to",
        "and",
        "or",
        "with",
        "get",
        "our",
        "all",
        "under",
        "up",
        "valid",
        "until",
        "till",
        "only",
        "rs",
        "inr",
    }
)

_UNIT_MULTIPLIERS: dict[str, float] = {
    "k": 1_000.0,
    "thousand": 1_000.0,
    "lakh": 100_000.0,
    "lakhs": 100_000.0,
    "lac": 100_000.0,
    "cr": 10_000_000.0,
    "crore": 10_000_000.0,
    "crores": 10_000_000.0,
    "m": 1_000_000.0,
}

_UPPER_BOUND_RE = re.compile(
    r"\b(?:under|up\s+to|below|maximum(?:\s+of)?|max|at\s+most|loans?\s+of)\s+"
    r"((?:₹|Rs\.?\s*|\$)?\s*(\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*(k|thousand|lakh|lakhs|lac|cr|crore|crores|m))?\b)",
    re.IGNORECASE,
)

_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

_FLAT_DISCOUNT_TAX_INCL_RE = re.compile(
    r"flat\s+(\d+(?:\.\d+)?)\s*%\s*off\b[^.\n]*inclusive\s+of\s+all\s+taxes",
    re.IGNORECASE,
)
_ADDED_GST_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*gst\s+(?:applies|extra|additional|charged)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class BoundSpec:
    raw_text: str
    value: float
    span: Span


def _parse_indian_amount(num_str: str, unit_str: str | None) -> float:
    clean = float(num_str.replace(",", ""))
    mult = _UNIT_MULTIPLIERS.get((unit_str or "").lower(), 1.0)
    return clean * mult


def _extract_upper_bounds(text: str) -> tuple[BoundSpec, ...]:
    bounds: list[BoundSpec] = []
    for m in _UPPER_BOUND_RE.finditer(text):
        val = _parse_indian_amount(m.group(2), m.group(3))
        bounds.append(
            BoundSpec(
                raw_text=m.group(0).strip(),
                value=val,
                span=Span(start=m.start(1), end=m.end(1)),
            )
        )
    return tuple(bounds)


def _content_keywords(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


class ClaimAlgebraCheck(Check):
    check_id: ClassVar[str] = "claim.algebra"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, TextNode)
        findings: list[Finding] = []

        # 1. Check self-contradictory tax-inclusive discount vs added GST
        findings.extend(self._check_tax_discount_contradiction(node))

        if not canon.facts:
            return findings

        node_kw = _content_keywords(node.text)
        for fact in canon.facts:
            fact_full = " ".join([fact.text, *fact.conditions])
            fact_kw = _content_keywords(fact_full)
            if len(node_kw & fact_kw) < 2:
                continue

            findings.extend(self._check_upper_bound_breach(node, canon, fact, fact_full))
            findings.extend(self._check_expiry_date_breach(node, canon, fact))

        return findings

    def _check_upper_bound_breach(
        self,
        node: TextNode,
        canon: Canon,
        fact: FactClaim,
        fact_full: str,
    ) -> list[Finding]:
        canon_bounds = _extract_upper_bounds(fact_full)
        if not canon_bounds:
            return []
        draft_bounds = _extract_upper_bounds(node.text)
        if not draft_bounds:
            return []

        canon_cap = canon_bounds[0]
        # Extract the canonical amount substring (e.g. "Rs 50,000") for replacement
        canon_amt_str = canon_cap.span.slice(fact_full)
        out: list[Finding] = []

        for d_bound in draft_bounds:
            if d_bound.value > canon_cap.value:
                witness = 0.5 * (canon_cap.value + d_bound.value)
                out.append(
                    self.finding(
                        node=node,
                        locator=d_bound.span,
                        severity=85,
                        message=(
                            f"SMT / Algebraic cap breach: draft permits up to "
                            f"{d_bound.value:,.0f} ({d_bound.raw_text!r}), violating Canon "
                            f"upper bound <= {canon_cap.value:,.0f} ({canon_cap.raw_text!r})."
                        ),
                        rule_ref=canon.to_rule_ref(fact),
                        evidence=AlgebraicProofEvidence(
                            draft_expr=f"amount <= {d_bound.value:.0f}",
                            canon_constraint=f"amount <= {canon_cap.value:.0f}",
                            solver_status="sat_counterexample",
                            counterexample={
                                "witness_amount": f"{witness:.0f}",
                                "draft_upper_bound": f"{d_bound.value:.0f}",
                                "canon_upper_bound": f"{canon_cap.value:.0f}",
                            },
                        ),
                        suggestion=Suggestion(
                            label=f"Clamp bound to {canon_amt_str}",
                            replacements=(
                                Replace(span=d_bound.span, replacement=canon_amt_str),
                            ),
                        ),
                        trace=Trace(tier=Tier.SMT),
                    )
                )
        return out

    def _check_expiry_date_breach(
        self,
        node: TextNode,
        canon: Canon,
        fact: FactClaim,
    ) -> list[Finding]:
        if not fact.valid_until:
            return []
        canon_date = fact.valid_until.strip()
        out: list[Finding] = []
        for match in _ISO_DATE_RE.finditer(node.text):
            draft_date = match.group(1)
            if draft_date > canon_date:
                span = Span(start=match.start(1), end=match.end(1))
                out.append(
                    self.finding(
                        node=node,
                        locator=span,
                        severity=80,
                        message=(
                            f"Temporal constraint breach: draft validity date {draft_date} "
                            f"exceeds Canon expiry date {canon_date}."
                        ),
                        rule_ref=canon.to_rule_ref(fact),
                        evidence=AlgebraicProofEvidence(
                            draft_expr=f"date <= {draft_date}",
                            canon_constraint=f"date <= {canon_date}",
                            solver_status="sat_counterexample",
                            counterexample={
                                "draft_date": draft_date,
                                "canon_valid_until": canon_date,
                            },
                        ),
                        suggestion=Suggestion(
                            label=f"Use approved expiry date {canon_date}",
                            replacements=(Replace(span=span, replacement=canon_date),),
                        ),
                        trace=Trace(tier=Tier.SMT),
                    )
                )
        return out

    def _check_tax_discount_contradiction(self, node: TextNode) -> list[Finding]:
        disc_match = _FLAT_DISCOUNT_TAX_INCL_RE.search(node.text)
        gst_match = _ADDED_GST_RE.search(node.text)
        if disc_match is None or gst_match is None:
            return []

        claimed_pct = float(disc_match.group(1))
        gst_pct = float(gst_match.group(1))
        net_multiplier = (1.0 - claimed_pct / 100.0) * (1.0 + gst_pct / 100.0)
        effective_pct = round((1.0 - net_multiplier) * 100.0, 2)

        if effective_pct >= claimed_pct:
            return []

        rule_ref = Rule(
            rule_id="ccpa-drip-pricing-discount-math",
            rule_type="fact",
            source_text=(
                "CCPA Dark Patterns (Drip Pricing): tax-inclusive headline discounts must "
                "equal the net post-GST discount."
            ),
        )
        span = Span(start=disc_match.start(1), end=disc_match.end(1))
        return [
            self.finding(
                node=node,
                locator=Span(start=disc_match.start(), end=gst_match.end()),
                severity=85,
                message=(
                    f"Algebraic discount contradiction: claiming {claimed_pct:.0f}% off "
                    f"(inclusive of all taxes) while adding {gst_pct:.0f}% GST yields an "
                    f"effective discount of only {effective_pct:.2f}%."
                ),
                rule_ref=rule_ref,
                evidence=AlgebraicProofEvidence(
                    draft_expr=f"discount == {claimed_pct:.2f}%",
                    canon_constraint=(
                        f"1 - (1 - {claimed_pct / 100:.2f}) * (1 + {gst_pct / 100:.2f}) "
                        f"== {effective_pct:.2f}%"
                    ),
                    solver_status="sat_counterexample",
                    counterexample={
                        "claimed_discount_pct": f"{claimed_pct:.2f}%",
                        "added_gst_pct": f"{gst_pct:.2f}%",
                        "effective_net_discount_pct": f"{effective_pct:.2f}%",
                    },
                ),
                suggestion=Suggestion(
                    label=f"State true net discount {effective_pct:.2f}%",
                    replacements=(Replace(span=span, replacement=f"{effective_pct:.2f}"),),
                ),
                trace=Trace(tier=Tier.SMT),
            )
        ]
