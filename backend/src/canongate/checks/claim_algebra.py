"""Tier 1.5 Check: SMT / Algebraic & Temporal Constraint Verifier (`claim.algebra`).

Verifies mathematical, currency-cap (Indian numbering: Lakh, Crore), temporal
(`valid_until`), and stacked-tax discount equations in `TextNode`s and across
multi-node `ContentAST` bundles (`run_bundle`):
1. **Upper-Bound Cap Breach (Z3 SMT / Interval Solver):** Proves
   $\\exists x \\in (C_{\\text{max}}, D_{\\text{max}}]:$
   $P_{\\text{draft}}(x) \\land \\neg P_{\\text{canon}}(x)$
   using `z3-solver` (`z3.Real`, `z3.Solver`) when installed, with an exact interval
   witness fallback.
2. **Temporal Expiry Breach:** Proves `draft_valid_until > canon.valid_until`
   on ISO date claims (`YYYY-MM-DD`).
3. **Stacked Tax / Net Discount Contradiction (FirstCry CCPA PIB 2171807):**
   Proves $1 - (1 - d)(1 + g) < d$ both when an explicit GST rate (`"18% GST applies"`)
   is stated AND when the exact FirstCry wording (`"27% discount — MRP inclusive of all taxes"`
   paired with `"GST and Add'l charges may apply on discounted price"`, where India's
   12% retail apparel GST drops a 27% discount to 18.24%) appears within a single node
   or across separate headline and footnote nodes in a bundle!
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from canongate.domain.ast import ContentAST, Node, NodeKind, TextNode
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

# Matches both "Flat 27% Off ... inclusive of all taxes" and FirstCry's
# "27% discount on MRP (inclusive of all taxes)" or "MRP inclusive of all taxes ... 27% off"
_DISCOUNT_PCT_RE = re.compile(
    r"(?:flat\s+)?(\d+(?:\.\d+)?)\s*%\s*(?:off|discount)\b",
    re.IGNORECASE,
)
_TAX_INCLUSIVE_RE = re.compile(
    r"\b(?:mrp\s+)?inclusive\s+of\s+all\s+taxes\b",
    re.IGNORECASE,
)
# Matches explicit ("18% GST applies") or implicit FirstCry
# ("GST and Add'l charges may apply on discounted price")
_ADDED_GST_RE = re.compile(
    r"(?:(\d+(?:\.\d+)?)\s*%\s*)?\bgst\s+"
    r"(?:and\s+add(?:'|’|itio)?(?:na)?l\s+charges\s+)?"
    r"(?:may\s+apply|applies|extra|additional|charged)"
    r"(?:\s+on\s+discounted\s+price)?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class BoundSpec:
    raw_text: str
    value: float
    span: Span


def _prove_upper_bound_sat(draft_val: float, canon_val: float) -> tuple[bool, float, str]:
    """Prove exists x: (x <= draft_val) AND NOT (x <= canon_val) via Z3 SMT or interval solver."""
    try:
        import z3  # type: ignore[import-not-found]

        x = z3.Real("amount")
        solver = z3.Solver()
        solver.add(x > 0)
        solver.add(x <= draft_val)
        solver.add(z3.Not(x <= canon_val))
        if solver.check() == z3.sat:
            return True, 0.5 * (canon_val + draft_val), "z3-smt-v4"
        return False, 0.0, "z3-smt-v4"
    except ImportError:
        if draft_val > canon_val:
            return True, 0.5 * (canon_val + draft_val), "interval-smt-v1"
        return False, 0.0, "interval-smt-v1"


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
    check_version: ClassVar[str] = "1.1"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, TextNode)
        findings: list[Finding] = []

        # 1. Check self-contradictory tax-inclusive discount vs added GST within a single node
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

    def run_bundle(self, ast: ContentAST, canon: Canon) -> list[Finding]:
        """Cross-node check for FirstCry-style headline vs footnote Drip Pricing contradiction."""
        text_nodes = ast.text_nodes()
        if len(text_nodes) < 2:
            return []

        headline_node: TextNode | None = None
        disc_match: re.Match[str] | None = None
        for tn in text_nodes:
            if _TAX_INCLUSIVE_RE.search(tn.text):
                dm = _DISCOUNT_PCT_RE.search(tn.text)
                if dm is not None and _ADDED_GST_RE.search(tn.text) is None:
                    headline_node = tn
                    disc_match = dm
                    break

        if headline_node is None or disc_match is None:
            return []

        for tn in text_nodes:
            if tn.id == headline_node.id:
                continue
            gst_match = _ADDED_GST_RE.search(tn.text)
            if gst_match is not None:
                return [
                    self._build_tax_discount_finding(
                        target_node=headline_node,
                        disc_match=disc_match,
                        gst_match=gst_match,
                        locator=Span(start=disc_match.start(), end=disc_match.end()),
                    )
                ]
        return []

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
        canon_amt_str = canon_cap.span.slice(fact_full)
        out: list[Finding] = []

        for d_bound in draft_bounds:
            is_sat, witness, solver_sha = _prove_upper_bound_sat(d_bound.value, canon_cap.value)
            if is_sat:
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
                            replacements=(Replace(span=d_bound.span, replacement=canon_amt_str),),
                        ),
                        trace=Trace(tier=Tier.SMT, model_sha=solver_sha),
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
                        trace=Trace(tier=Tier.SMT, model_sha="temporal-smt-v1"),
                    )
                )
        return out

    def _check_tax_discount_contradiction(self, node: TextNode) -> list[Finding]:
        if not _TAX_INCLUSIVE_RE.search(node.text):
            return []
        disc_match = _DISCOUNT_PCT_RE.search(node.text)
        gst_match = _ADDED_GST_RE.search(node.text)
        if disc_match is None or gst_match is None:
            return []

        loc_start = min(disc_match.start(), gst_match.start())
        loc_end = max(disc_match.end(), gst_match.end())
        return [
            self._build_tax_discount_finding(
                target_node=node,
                disc_match=disc_match,
                gst_match=gst_match,
                locator=Span(start=loc_start, end=loc_end),
            )
        ]

    def _build_tax_discount_finding(
        self,
        *,
        target_node: TextNode,
        disc_match: re.Match[str],
        gst_match: re.Match[str],
        locator: Span,
    ) -> Finding:
        claimed_pct = float(disc_match.group(1))
        # Default to 12.0% GST (FirstCry CCPA PIB 2171807 standard apparel
        # slab -> 27% drops to 18.24%) when the footnote states
        # "GST and Add'l charges may apply on discounted price"
        # without an explicit percentage number.
        gst_pct = float(gst_match.group(1)) if gst_match.group(1) else 12.0
        net_multiplier = (1.0 - claimed_pct / 100.0) * (1.0 + gst_pct / 100.0)
        effective_pct = round((1.0 - net_multiplier) * 100.0, 2)

        rule_ref = Rule(
            rule_id="ccpa-drip-pricing-discount-math",
            rule_type="fact",
            source_text=(
                "CCPA Dark Patterns (Drip Pricing, PIB 2171807): tax-inclusive headline "
                "discounts must equal the net post-GST discount."
            ),
        )
        span = Span(start=disc_match.start(1), end=disc_match.end(1))
        return self.finding(
            node=target_node,
            locator=locator,
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
            trace=Trace(tier=Tier.SMT, model_sha="drip-pricing-smt-v1"),
        )
