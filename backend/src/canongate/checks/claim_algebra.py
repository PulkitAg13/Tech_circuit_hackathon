"""Tier 1.5 Check: SMT / Algebraic, KFS Validity & Temporal Constraint Verifier (`claim.algebra`).

Implements formal symbolic constraint solving (`SmtConstraintSolver`) backed by:
1. **Primary Solver — Z3 Theorem Prover (`z3-solver`):**
   Uses `z3.Real`, `z3.Int`, `z3.Solver`, `z3.And`, `z3.Not`, and `solver.model().eval(...)`
   over Linear and Nonlinear Real Arithmetic (`QF_NRA` / `QF_LRA`).
2. **Secondary Solver — SymPy Rational Interval + SciPy HiGHS LP Solver (`sympy-scipy-smt-v2`):**
   When the native Z3 C++ wheel is absent, symbolically intersects exact rational intervals
   via `sympy.Interval` & `sympy.Rational` and computes exact interior counterexample
   witnesses via `scipy.optimize.linprog(method="highs")`.

Proves five classes of regulatory and mathematical violations:
- **Upper-Bound Cap Breach:** $\\exists x > 0 : (x \\le D_{\\max}) \\land \\neg(x \\le C_{\\max})$
  (Indian numbering: Lakh, Crore, Rs, ₹, plus structured `FactClaim.metric_value` & `<=`).
- **Lower-Bound Floor Breach:**
  $\\exists x > 0 : (x \\ge D_{\\min}) \\land \\neg(x \\ge C_{\\min})$.
- **RBI 2025 KFS Validity Window Breach:** Verifies `kfs_acceptance_validity_days` bounds.
- **Temporal Expiry Breach:** Proves `draft_valid_until > canon.valid_until` over ordinal days.
- **Stacked Tax / Net Discount Contradiction (FirstCry CCPA PIB 2171807):**
  Proves $d_{\\text{net}} = (1 - (1 - d)(1 + g)) \\cdot 100 < d \\cdot 100$
  both within a single node and across separate headline/footnote nodes (`run_bundle`).
"""

from __future__ import annotations

import datetime as dt
import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import ClassVar, Literal

import numpy as np

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
from canongate.engine.nlp import content_words, normalize_stem

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

_LOWER_BOUND_RE = re.compile(
    r"\b(?:minimum(?:\s+of)?|min|at\s+least|starting\s+from|above|over|more\s+than)\s+"
    r"((?:₹|Rs\.?\s*|\$)?\s*(\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*(k|thousand|lakh|lakhs|lac|cr|crore|crores|m))?\b)",
    re.IGNORECASE,
)

_DAYS_VALIDITY_RE = re.compile(
    r"\b(?:valid\s+for|validity\s*(?:of|:)?|within|for)\s+((\d+)\s*days?)\b",
    re.IGNORECASE,
)

_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

_DISCOUNT_PCT_RE = re.compile(
    r"(?:flat\s+)?(\d+(?:\.\d+)?)\s*%\s*(?:off|discount)\b",
    re.IGNORECASE,
)
_TAX_INCLUSIVE_RE = re.compile(
    r"\b(?:mrp\s+)?inclusive\s+of\s+all\s+taxes\b",
    re.IGNORECASE,
)
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
    kind: Literal["upper", "lower"] = "upper"


def _parse_indian_amount(num_str: str, unit_str: str | None) -> float:
    clean = float(num_str.replace(",", ""))
    mult = _UNIT_MULTIPLIERS.get((unit_str or "").lower(), 1.0)
    return clean * mult


_Z3_LOCK = threading.Lock()


class SmtConstraintSolver:
    """Formal SMT / symbolic arithmetic constraint solver (`z3` -> `sympy` + `scipy` HiGHS)."""

    @staticmethod
    @lru_cache(maxsize=512)
    def prove_upper_bound_breach(draft_val: float, canon_val: float) -> tuple[bool, float, str]:
        """Prove $\\exists x > 0 : (x \\le D_{\\max}) \\land \\neg(x \\le C_{\\max})$."""
        try:
            import z3  # type: ignore[import-not-found]

            with _Z3_LOCK:
                x = z3.Real("amount")
                solver = z3.Solver()
                solver.add(x > 0)
                solver.add(x <= draft_val)
                solver.add(z3.Not(x <= canon_val))
                solver.add(x >= canon_val + 0.5 * (draft_val - canon_val))
                if solver.check() == z3.sat:
                    model = solver.model()
                    val = model.eval(x, model_completion=True)
                    witness = (
                        float(val.as_fraction())
                        if hasattr(val, "as_fraction")
                        else 0.5 * (canon_val + draft_val)
                    )
                    return True, witness, "z3-smt-v4"
                return False, 0.0, "z3-smt-v4"
        except ImportError:
            pass

        try:
            import sympy as sp
            from scipy.optimize import linprog

            d_rat = sp.Rational(str(draft_val))
            c_rat = sp.Rational(str(canon_val))
            sol_set = sp.Interval(0, d_rat, left_open=True) & sp.Interval(
                c_rat, sp.oo, left_open=True
            )
            if sol_set.is_empty:
                return False, 0.0, "sympy-scipy-smt-v2"

            # Find interior witness maximizing distance above canon_val via HiGHS LP
            eps = max(1e-3, 0.5 * (draft_val - canon_val))
            lp = linprog(
                c=[-1.0],
                A_ub=np.array([[1.0], [-1.0]], dtype=np.float64),
                b_ub=np.array([draft_val, -(canon_val + eps)], dtype=np.float64),
                bounds=(0.0, None),
                method="highs",
            )
            witness = (
                float(lp.x[0])
                if (lp.success and lp.x is not None)
                else 0.5 * (canon_val + draft_val)
            )
            return True, min(witness, 0.5 * (canon_val + draft_val)), "sympy-scipy-smt-v2"
        except Exception:
            if draft_val > canon_val:
                return True, 0.5 * (canon_val + draft_val), "interval-smt-v1"
            return False, 0.0, "interval-smt-v1"

    @staticmethod
    @lru_cache(maxsize=512)
    def prove_lower_bound_breach(draft_val: float, canon_val: float) -> tuple[bool, float, str]:
        """Prove $\\exists x > 0 : (x \\ge D_{\\min}) \\land \\neg(x \\ge C_{\\min})$."""
        try:
            import z3  # type: ignore[import-not-found]

            with _Z3_LOCK:
                x = z3.Real("amount")
                solver = z3.Solver()
                solver.add(x > 0)
                solver.add(x >= draft_val)
                solver.add(z3.Not(x >= canon_val))
                if solver.check() == z3.sat:
                    return True, 0.5 * (draft_val + canon_val), "z3-smt-v4"
                return False, 0.0, "z3-smt-v4"
        except ImportError:
            pass

        try:
            import sympy as sp

            d_rat = sp.Rational(str(draft_val))
            c_rat = sp.Rational(str(canon_val))
            sol_set = sp.Interval(max(sp.Integer(0), d_rat), sp.oo) & sp.Interval(
                0, c_rat, left_open=True, right_open=True
            )
            if not sol_set.is_empty:
                return True, 0.5 * (draft_val + canon_val), "sympy-scipy-smt-v2"
            return False, 0.0, "sympy-scipy-smt-v2"
        except Exception:
            if draft_val < canon_val:
                return True, 0.5 * (draft_val + canon_val), "interval-smt-v1"
            return False, 0.0, "interval-smt-v1"

    @staticmethod
    @lru_cache(maxsize=512)
    def prove_temporal_expiry_breach(draft_iso: str, canon_iso: str) -> tuple[bool, str, str]:
        r"""Prove $\exists t \in \mathbb{Z}$ such that:
        $(t \le t_{\text{draft}}) \land \neg(t \le t_{\text{canon}})$.
        """
        try:
            d_ord = dt.date.fromisoformat(draft_iso).toordinal()
            c_ord = dt.date.fromisoformat(canon_iso).toordinal()
        except ValueError:
            return (draft_iso > canon_iso), draft_iso, "temporal-smt-v1"

        try:
            import z3  # type: ignore[import-not-found]

            with _Z3_LOCK:
                t = z3.Int("epoch_day")
                solver = z3.Solver()
                solver.add(t <= d_ord)
                solver.add(z3.Not(t <= c_ord))
                if solver.check() == z3.sat:
                    return True, draft_iso, "z3-smt-v4"
                return False, "", "z3-smt-v4"
        except ImportError:
            pass

        try:
            import sympy as sp

            sol_set = sp.Interval(-sp.oo, sp.Integer(d_ord)) & sp.Interval(
                sp.Integer(c_ord), sp.oo, left_open=True
            )
            if not sol_set.is_empty:
                return True, draft_iso, "sympy-scipy-smt-v2"
            return False, "", "sympy-scipy-smt-v2"
        except Exception:
            return (d_ord > c_ord), draft_iso, "temporal-smt-v1"

    @staticmethod
    @lru_cache(maxsize=512)
    def prove_drip_pricing_contradiction(
        claimed_pct: float,
        gst_pct: float,
    ) -> tuple[bool, float, str]:
        """Prove $d_{\\text{eff}} = (1 - (1 - d)(1 + g)) \\cdot 100 < d \\cdot 100$."""
        try:
            import z3  # type: ignore[import-not-found]

            with _Z3_LOCK:
                d_eff = z3.Real("effective_pct")
                solver = z3.Solver()
                net_mult = (1.0 - claimed_pct / 100.0) * (1.0 + gst_pct / 100.0)
                exact_eff = round((1.0 - net_mult) * 100.0, 2)
                solver.add(d_eff == exact_eff)
                solver.add(z3.Not(d_eff >= claimed_pct))
                if solver.check() == z3.sat:
                    return True, exact_eff, "z3-smt-v4"
                return False, exact_eff, "z3-smt-v4"
        except ImportError:
            pass

        try:
            import sympy as sp

            d_r = sp.Rational(str(claimed_pct)) / sp.Integer(100)
            g_r = sp.Rational(str(gst_pct)) / sp.Integer(100)
            eff_r = (sp.Integer(1) - (sp.Integer(1) - d_r) * (sp.Integer(1) + g_r)) * sp.Integer(
                100
            )
            sol_set = sp.FiniteSet(eff_r) & sp.Interval(
                -sp.oo, sp.Rational(str(claimed_pct)), right_open=True
            )
            eff_float = round(float(eff_r), 2)
            return (not sol_set.is_empty), eff_float, "sympy-scipy-smt-v2"
        except Exception:
            net_mult = (1.0 - claimed_pct / 100.0) * (1.0 + gst_pct / 100.0)
            eff_float = round((1.0 - net_mult) * 100.0, 2)
            return (eff_float < claimed_pct), eff_float, "drip-pricing-smt-v1"


default_smt_solver = SmtConstraintSolver()


def _extract_bounds(
    text: str,
    pattern: re.Pattern[str],
    kind: Literal["upper", "lower"],
) -> tuple[BoundSpec, ...]:
    return tuple(
        BoundSpec(
            raw_text=m.group(0).strip(),
            value=_parse_indian_amount(m.group(2), m.group(3)),
            span=Span(start=m.start(1), end=m.end(1)),
            kind=kind,
        )
        for m in pattern.finditer(text)
    )


def _extract_upper_bounds(text: str) -> tuple[BoundSpec, ...]:
    return _extract_bounds(text, _UPPER_BOUND_RE, "upper")


def _extract_lower_bounds(text: str) -> tuple[BoundSpec, ...]:
    return _extract_bounds(text, _LOWER_BOUND_RE, "lower")


def _resolve_canon_bound(
    fact: FactClaim,
    fact_full: str,
    kind: Literal["upper", "lower"],
) -> BoundSpec | None:
    bounds = (
        _extract_upper_bounds(fact_full) if kind == "upper" else _extract_lower_bounds(fact_full)
    )
    if bounds:
        return bounds[0]
    ops = ("<=", "<") if kind == "upper" else (">=", ">")
    if fact.comparison_operator in ops and fact.metric_value:
        m = re.search(
            r"(\d[\d,]*(?:\.\d+)?)(?:\s*(k|thousand|lakh|lakhs|lac|cr|crore|crores|m))?",
            fact.metric_value,
            re.IGNORECASE,
        )
        if m:
            return BoundSpec(
                raw_text=fact.metric_value,
                value=_parse_indian_amount(m.group(1), m.group(2)),
                span=Span(start=0, end=len(fact.metric_value)),
                kind=kind,
            )
    return None


def _content_stems(text: str) -> set[str]:
    return {normalize_stem(w) for w in content_words(text)}


class ClaimAlgebraCheck(Check):
    check_id: ClassVar[str] = "claim.algebra"
    check_version: ClassVar[str] = "2.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, TextNode)
        findings: list[Finding] = []

        # 1. Check self-contradictory tax-inclusive discount vs added GST within a single node
        findings.extend(self._check_tax_discount_contradiction(node))

        if not canon.facts:
            return findings

        node_stems = _content_stems(node.text)
        for fact in canon.facts:
            fact_full = " ".join([fact.text, *fact.conditions, fact.subject_product])
            fact_stems = _content_stems(fact_full)
            if len(node_stems & fact_stems) < 2:
                continue

            findings.extend(self._check_upper_bound_breach(node, canon, fact, fact_full))
            findings.extend(self._check_lower_bound_breach(node, canon, fact, fact_full))
            findings.extend(self._check_kfs_validity_days_breach(node, canon, fact))
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
        canon_cap = _resolve_canon_bound(fact, fact_full, "upper")
        if canon_cap is None:
            return []
        draft_bounds = _extract_upper_bounds(node.text)
        if not draft_bounds:
            return []
        canon_amt_str = (
            canon_cap.span.slice(fact_full)
            if canon_cap.span.end <= len(fact_full) and canon_cap.raw_text in fact_full
            else canon_cap.raw_text
        )
        out: list[Finding] = []

        for d_bound in draft_bounds:
            is_sat, witness, solver_sha = default_smt_solver.prove_upper_bound_breach(
                d_bound.value, canon_cap.value
            )
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

    def _check_lower_bound_breach(
        self,
        node: TextNode,
        canon: Canon,
        fact: FactClaim,
        fact_full: str,
    ) -> list[Finding]:
        canon_floor = _resolve_canon_bound(fact, fact_full, "lower")
        if canon_floor is None:
            return []
        draft_bounds = _extract_lower_bounds(node.text)
        if not draft_bounds:
            return []
        canon_amt_str = (
            canon_floor.span.slice(fact_full)
            if canon_floor.span.end <= len(fact_full) and canon_floor.raw_text in fact_full
            else canon_floor.raw_text
        )
        out: list[Finding] = []

        for d_bound in draft_bounds:
            is_sat, witness, solver_sha = default_smt_solver.prove_lower_bound_breach(
                d_bound.value, canon_floor.value
            )
            if is_sat:
                out.append(
                    self.finding(
                        node=node,
                        locator=d_bound.span,
                        severity=85,
                        message=(
                            f"SMT / Algebraic floor breach: draft permits down to "
                            f"{d_bound.value:,.0f} ({d_bound.raw_text!r}), violating Canon "
                            f"lower bound >= {canon_floor.value:,.0f} ({canon_floor.raw_text!r})."
                        ),
                        rule_ref=canon.to_rule_ref(fact),
                        evidence=AlgebraicProofEvidence(
                            draft_expr=f"amount >= {d_bound.value:.0f}",
                            canon_constraint=f"amount >= {canon_floor.value:.0f}",
                            solver_status="sat_counterexample",
                            counterexample={
                                "witness_amount": f"{witness:.0f}",
                                "draft_lower_bound": f"{d_bound.value:.0f}",
                                "canon_lower_bound": f"{canon_floor.value:.0f}",
                            },
                        ),
                        suggestion=Suggestion(
                            label=f"Raise floor to {canon_amt_str}",
                            replacements=(Replace(span=d_bound.span, replacement=canon_amt_str),),
                        ),
                        trace=Trace(tier=Tier.SMT, model_sha=solver_sha),
                    )
                )
        return out

    def _check_kfs_validity_days_breach(
        self,
        node: TextNode,
        canon: Canon,
        fact: FactClaim,
    ) -> list[Finding]:
        if fact.kfs_acceptance_validity_days is None:
            return []
        min_days = int(fact.kfs_acceptance_validity_days)
        out: list[Finding] = []
        for match in _DAYS_VALIDITY_RE.finditer(node.text):
            draft_days = int(match.group(2))
            is_sat, witness, solver_sha = default_smt_solver.prove_lower_bound_breach(
                float(draft_days), float(min_days)
            )
            if is_sat:
                span = Span(start=match.start(1), end=match.end(1))
                out.append(
                    self.finding(
                        node=node,
                        locator=span,
                        severity=80,
                        message=(
                            f"RBI 2025 KFS validity window breach: draft gives {draft_days} days, "
                            f"below mandatory KFS minimum {min_days} days."
                        ),
                        rule_ref=canon.to_rule_ref(fact),
                        evidence=AlgebraicProofEvidence(
                            draft_expr=f"kfs_validity_days == {draft_days}",
                            canon_constraint=f"kfs_validity_days >= {min_days}",
                            solver_status="sat_counterexample",
                            counterexample={
                                "witness_days": f"{witness:.1f}",
                                "draft_days": str(draft_days),
                                "canon_min_days": str(min_days),
                            },
                        ),
                        suggestion=Suggestion(
                            label=f"Set KFS validity to {min_days} days",
                            replacements=(Replace(span=span, replacement=f"{min_days} days"),),
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
            is_sat, _, solver_sha = default_smt_solver.prove_temporal_expiry_breach(
                draft_date, canon_date
            )
            if is_sat:
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
                        trace=Trace(tier=Tier.SMT, model_sha=solver_sha),
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
        gst_pct = float(gst_match.group(1)) if gst_match.group(1) else 12.0
        _, effective_pct, solver_sha = default_smt_solver.prove_drip_pricing_contradiction(
            claimed_pct, gst_pct
        )

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
            trace=Trace(tier=Tier.SMT, model_sha=solver_sha),
        )
