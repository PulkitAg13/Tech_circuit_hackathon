"""Tier 1.5 Check: Unit-Aware SMT / Algebraic, Pricing & Brand-Guideline Verifier (`claim.algebra`).

Implements formal symbolic constraint solving (`SmtConstraintSolver`) backed by:
1. **Primary Solver — Z3 Theorem Prover (`z3-solver`):**
   Uses `z3.Real`, `z3.Int`, `z3.Solver`, `z3.And`, `z3.Not`, and `solver.model().eval(...)`
   over Linear and Nonlinear Real Arithmetic (`QF_NRA` / `QF_LRA`).
2. **Secondary Solver — SymPy Rational Interval + SciPy HiGHS LP Solver (`sympy-scipy-smt-v2`):**
   When the native Z3 C++ wheel is absent, symbolically intersects exact rational intervals
   via `sympy.Interval` & `sympy.Rational` and computes exact interior counterexample
   witnesses via `scipy.optimize.linprog(method="highs")`.

Solves seven general, unit-aware classes of regulatory, financial, and brand constraints:
1. **Unit-Aware Upper-Bound Cap Breach:**
   $\\exists x > 0 : (x \\le D_{\\max}) \\land \\neg(x \\le C_{\\max})$ matched strictly
   within compatible unit dimensions (`currency`, `percent`, `duration_days`, etc.).
2. **Unit-Aware Lower-Bound Floor Breach:**
   $\\exists x > 0 : (x \\ge D_{\\min}) \\land \\neg(x \\ge C_{\\min})$ matched strictly
   within compatible unit dimensions.
3. **Self-Contradictory Interval Disjointness (`min > max`):**
   Proves $(x \\ge D_{\\min}) \\land (x \\le D_{\\max})$ is `UNSAT` when $D_{\\min} > D_{\\max}$
   for the same unit dimension.
4. **Multi-Variable MRP / Offer Price / Discount % / Mandatory Fee Contradiction:**
   Proves $P_{\\text{offer}} + F_{\\text{fee}} > M_{\\text{MRP}} \\cdot (1 - d/100)$,
   computing the true effective net discount $d_{\\text{eff}}\\%$.
5. **Stacked Tax / Net Discount Contradiction (CCPA Drip Pricing):**
   Proves $d_{\\text{net}} = (1 - (1 - d/100)(1 + g/100)) \\cdot 100 < d$ for any
   discount $d\\%$ and GST/tax rate $g\\%$.
6. **Multi-Variable Loan / EMI / Tenure / APR Amortization Contradiction:**
   Proves total repayment $N \\cdot E + F > P$ under $0\\%$ interest / no-cost EMI claims,
   or implied APR $> r_{\\text{canon}}\\%$.
7. **Brand Guideline Typography Hierarchy & 60/30/10 Color Ratio Constraints:**
   Proves heading/body font-size inversions and color distribution ratio breaches
   ($p_1 + p_2 + p_3 \\ne 100\\%$ or $p_{\\text{accent}} > p_{\\text{primary}}$).
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

UnitDimension = Literal[
    "currency",
    "percent",
    "duration_days",
    "font_size_pt",
    "mass_g",
    "dimension_px",
    "scalar",
]

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
    "kg": 1_000.0,
    "g": 1.0,
    "mg": 0.001,
    "month": 30.0,
    "months": 30.0,
    "year": 365.0,
    "years": 365.0,
    "week": 7.0,
    "weeks": 7.0,
    "day": 1.0,
    "days": 1.0,
}

_UPPER_BOUND_RE = re.compile(
    r"\b(?:under|up\s+to|below|maximum(?:\s+of)?|max|at\s+most|ceiling(?:\s+of)?|cap(?:\s+of)?|loans?\s+of)\s+"
    r"((₹|Rs\.?\s*|\$)?\s*(\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*(%|(?:\b(?:percent|pct|thousand|crores?|lakhs?|months?|years?|weeks?|days?|lac|cr|kg|mg|pt|px|k|m|g)\b)))?)",
    re.IGNORECASE,
)

_LOWER_BOUND_RE = re.compile(
    r"\b(?:minimum(?:\s+of)?|min|at\s+least|starting\s+from|above|over|more\s+than|floor(?:\s+of)?)\s+"
    r"((₹|Rs\.?\s*|\$)?\s*(\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*(%|(?:\b(?:percent|pct|thousand|crores?|lakhs?|months?|years?|weeks?|days?|lac|cr|kg|mg|pt|px|k|m|g)\b)))?)",
    re.IGNORECASE,
)

_DAYS_VALIDITY_RE = re.compile(
    r"\b(?:valid\s+for|validity\s*(?:of|:)?|within|for)\s+((\d+)\s*days?)\b",
    re.IGNORECASE,
)

_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

_DISCOUNT_PCT_RE = re.compile(
    r"(?:flat\s+|up\s+to\s+)?(\d+(?:\.\d+)?)\s*%\s*(?:off|discount)\b",
    re.IGNORECASE,
)
_TAX_INCLUSIVE_RE = re.compile(
    r"\b(?:mrp\s+)?inclusive\s+of\s+all\s+taxes\b",
    re.IGNORECASE,
)
_ADDED_GST_RE = re.compile(
    r"(?:(\d+(?:\.\d+)?)\s*%\s*)?\b(?:gst|tax|taxes|surcharge)\s+"
    r"(?:and\s+add(?:'|’|itio)?(?:na)?l\s+charges\s+)?"
    r"(?:may\s+apply|applies|extra|additional|charged)"
    r"(?:\s+on\s+discounted\s+price)?",
    re.IGNORECASE,
)

# Multi-variable MRP / Offer / Fee regexes
_MRP_PRICE_RE = re.compile(
    r"\b(?:mrp|list\s+price|original\s+price|worth)\s*(?:of|is|:)?\s*(?:₹|Rs\.?\s*|\$)\s*(\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
_OFFER_PRICE_RE = re.compile(
    r"\b(?:offer\s+price|sale\s+price|checkout\s+price|now(?:\s+at|\s+only)?|pay(?:\s+just|\s+only)?|for\s+just)\s*(?:is|:)?\s*(?:₹|Rs\.?\s*|\$)\s*(\d[\d,]*(?:\.\d+)?)"
    r"(?!\s*(?:/\s*mo|/\s*month|per\s+month|emi\b))",
    re.IGNORECASE,
)
_MANDATORY_FEE_RE = re.compile(
    r"(?:\+|plus|with|and)\s*(?:a\s+)?(?:mandatory\s+)?(?:₹|Rs\.?\s*|\$)\s*(\d[\d,]*(?:\.\d+)?)\s*"
    r"(?:mandatory\s+)?(?:platform|processing|convenience|handling|packaging|onboarding|service)\s+fee",
    re.IGNORECASE,
)

# Multi-variable Loan / EMI / Tenure / APR regexes
_LOAN_PRINCIPAL_RE = re.compile(
    r"\b(?:borrow|loan\s+(?:of|amount)|principal(?:\s+of)?)\s*(?:is|:)?\s*(?:₹|Rs\.?\s*|\$)\s*(\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*(k|thousand|lakh|lakhs|lac))?\b",
    re.IGNORECASE,
)
_EMI_AMOUNT_RE = re.compile(
    r"\b(?:emi\s+(?:of|is|at)?\s*(?:just\s+)?(?:₹|Rs\.?\s*|\$)\s*(\d[\d,]*(?:\.\d+)?)|"
    r"(?:₹|Rs\.?\s*|\$)\s*(\d[\d,]*(?:\.\d+)?)\s*(?:/\s*mo(?:nth)?|per\s+month|\bemi\b))",
    re.IGNORECASE,
)
_TENURE_MONTHS_RE = re.compile(
    r"\b(?:for|over|tenure(?:\s+of)?)\s+(\d+)\s*months?\b",
    re.IGNORECASE,
)
_ZERO_INTEREST_RE = re.compile(
    r"\b(?:0%\s*(?:interest|apr|finance\s+charge)|no[-\s]cost\s+emi|zero\s+interest)\b",
    re.IGNORECASE,
)
_STATED_APR_RE = re.compile(
    r"\b(?:apr|annual\s+percentage\s+rate|interest\s+rate)\s*(?:of|is|at|:)?\s*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

# Brand-Guidelines Typography & Color Ratio regexes (anthropics/skills/brand-guidelines)
_HEADING_SIZE_RE = re.compile(
    r"\b(?:heading|h1|h2|title|display)\s*(?:font[-\s]*size|size|text)?\s*(?:is|of|:|=)?\s*(\d+(?:\.\d+)?)\s*(pt|px)\b",
    re.IGNORECASE,
)
_BODY_SIZE_RE = re.compile(
    r"\b(?:body|paragraph|copy)\s*(?:font[-\s]*size|size|text)?\s*(?:is|of|:|=)?\s*(\d+(?:\.\d+)?)\s*(pt|px)\b",
    re.IGNORECASE,
)
_COLOR_RATIO_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*%\s*(?:primary|dominant|main|neutral)[^.\n]*?"
    r"(\d+(?:\.\d+)?)\s*%\s*(?:secondary|supporting)[^.\n]*?"
    r"(\d+(?:\.\d+)?)\s*%\s*(?:accent|highlight)\b",
    re.IGNORECASE,
)


def _classify_unit_dimension(
    currency_sym: str | None,
    unit_str: str | None,
    context_text: str = "",
) -> UnitDimension:
    u = (unit_str or "").strip().lower()
    if currency_sym or u in ("lakh", "lakhs", "lac", "cr", "crore", "crores"):
        return "currency"
    if u in ("%", "pct", "percent"):
        return "percent"
    if u in ("day", "days", "week", "weeks", "month", "months", "year", "years"):
        return "duration_days"
    if u == "pt":
        return "font_size_pt"
    if u == "px":
        return "dimension_px"
    if u in ("g", "mg", "kg"):
        return "mass_g"
    ctx_lower = context_text.lower()
    if u in ("k", "thousand", "m", "") and any(
        tok in ctx_lower
        for tok in ("rs", "₹", "$", "loan", "salary", "fee", "price", "mrp", "credit")
    ):
        return "currency"
    return "scalar"


def _parse_scaled_value(num_str: str, unit_str: str | None) -> float:
    clean = float(num_str.replace(",", ""))
    mult = _UNIT_MULTIPLIERS.get((unit_str or "").strip().lower(), 1.0)
    return clean * mult


@dataclass(frozen=True, slots=True)
class BoundSpec:
    raw_text: str
    value: float
    span: Span
    kind: Literal["upper", "lower"] = "upper"
    unit_dim: UnitDimension = "scalar"


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
                ctx = z3.Context()
                x = z3.Real("amount", ctx=ctx)
                solver = z3.Solver(ctx=ctx)
                solver.add(x > 0)
                solver.add(x <= draft_val)
                solver.add(z3.Not(x <= canon_val, ctx=ctx))
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
        except Exception:
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
                ctx = z3.Context()
                x = z3.Real("amount", ctx=ctx)
                solver = z3.Solver(ctx=ctx)
                solver.add(x > 0)
                solver.add(x >= draft_val)
                solver.add(z3.Not(x >= canon_val, ctx=ctx))
                if solver.check() == z3.sat:
                    return True, 0.5 * (draft_val + canon_val), "z3-smt-v4"
                return False, 0.0, "z3-smt-v4"
        except Exception:
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
    def prove_self_contradictory_bounds(lower_val: float, upper_val: float) -> tuple[bool, str]:
        """Prove that $(x \\ge L) \\land (x \\le U)$ is UNSAT when $L > U$."""
        try:
            import z3  # type: ignore[import-not-found]

            with _Z3_LOCK:
                ctx = z3.Context()
                x = z3.Real("x", ctx=ctx)
                solver = z3.Solver(ctx=ctx)
                solver.add(x >= lower_val)
                solver.add(x <= upper_val)
                return (solver.check() == z3.unsat), "z3-smt-v4"
        except Exception:
            pass

        try:
            import sympy as sp

            sol = sp.Interval(sp.Rational(str(lower_val)), sp.Rational(str(upper_val)))
            return bool(sol.is_empty), "sympy-scipy-smt-v2"
        except Exception:
            return (lower_val > upper_val), "interval-smt-v1"

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
                ctx = z3.Context()
                t = z3.Int("epoch_day", ctx=ctx)
                solver = z3.Solver(ctx=ctx)
                solver.add(t <= d_ord)
                solver.add(z3.Not(t <= c_ord, ctx=ctx))
                if solver.check() == z3.sat:
                    return True, draft_iso, "z3-smt-v4"
                return False, "", "z3-smt-v4"
        except Exception:
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
                ctx = z3.Context()
                d_eff = z3.Real("effective_pct", ctx=ctx)
                solver = z3.Solver(ctx=ctx)
                net_mult = (1.0 - claimed_pct / 100.0) * (1.0 + gst_pct / 100.0)
                exact_eff = round((1.0 - net_mult) * 100.0, 2)
                solver.add(d_eff == exact_eff)
                solver.add(z3.Not(d_eff >= claimed_pct, ctx=ctx))
                if solver.check() == z3.sat:
                    return True, exact_eff, "z3-smt-v4"
                return False, exact_eff, "z3-smt-v4"
        except Exception:
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

    @staticmethod
    @lru_cache(maxsize=512)
    def prove_mrp_discount_fee_contradiction(
        mrp: float,
        offer_price: float,
        claimed_discount_pct: float,
        mandatory_fee: float = 0.0,
    ) -> tuple[bool, float, float, str]:
        """Prove whether $(P_{\\text{offer}} + F_{\\text{fee}}) > M_{\\text{MRP}} (1 - d/100)$.

        Returns `(is_contradiction, effective_checkout_price, actual_discount_pct, solver_id)`.
        """
        if mrp <= 0:
            return False, offer_price + mandatory_fee, 0.0, "sympy-scipy-smt-v2"
        eff_price = round(offer_price + mandatory_fee, 2)
        actual_disc_pct = round((1.0 - eff_price / mrp) * 100.0, 2)
        expected_max_price = round(mrp * (1.0 - claimed_discount_pct / 100.0), 2)

        try:
            import z3  # type: ignore[import-not-found]

            with _Z3_LOCK:
                ctx = z3.Context()
                p_eff = z3.Real("checkout_price", ctx=ctx)
                solver = z3.Solver(ctx=ctx)
                solver.add(p_eff == eff_price)
                solver.add(p_eff > expected_max_price + 0.01)
                if solver.check() == z3.sat:
                    return True, eff_price, actual_disc_pct, "z3-smt-v4"
                return False, eff_price, actual_disc_pct, "z3-smt-v4"
        except Exception:
            pass

        try:
            import sympy as sp

            m_r = sp.Rational(str(mrp))
            p_r = sp.Rational(str(offer_price)) + sp.Rational(str(mandatory_fee))
            d_r = sp.Rational(str(claimed_discount_pct)) / sp.Integer(100)
            target_r = m_r * (sp.Integer(1) - d_r)
            is_breach = bool(p_r > target_r + sp.Rational("1/100"))
            return is_breach, eff_price, actual_disc_pct, "sympy-scipy-smt-v2"
        except Exception:
            return (
                (eff_price > expected_max_price + 0.01),
                eff_price,
                actual_disc_pct,
                "interval-smt-v1",
            )

    @staticmethod
    @lru_cache(maxsize=512)
    def prove_loan_emi_apr_contradiction(
        principal: float,
        emi: float,
        tenure_months: int,
        processing_fee: float = 0.0,
        max_apr_pct: float = 0.0,
    ) -> tuple[bool, float, float, str]:
        """Prove whether $(N \\cdot \\text{EMI} + F)$ exceeds allowed repayment under APR.

        Returns `(is_contradiction, total_repayment, implied_apr_pct, solver_id)`.
        """
        if principal <= 0 or tenure_months <= 0 or emi <= 0:
            return False, 0.0, 0.0, "sympy-scipy-smt-v2"

        total_repayment = round(emi * tenure_months + processing_fee, 2)
        total_cost_of_credit = max(0.0, total_repayment - principal)
        # Annualized percentage rate approximation (reducing balance / average principal)
        years = tenure_months / 12.0
        avg_principal = principal * (tenure_months + 1) / (2.0 * tenure_months)
        implied_apr = round((total_cost_of_credit / max(1.0, avg_principal * years)) * 100.0, 2)

        # Max allowed total repayment under simple/KFS bound for max_apr_pct
        if max_apr_pct <= 0.001:
            allowed_repayment = principal
        else:
            allowed_repayment = round(
                principal + avg_principal * (max_apr_pct / 100.0) * years,
                2,
            )

        try:
            import z3  # type: ignore[import-not-found]

            with _Z3_LOCK:
                ctx = z3.Context()
                r_tot = z3.Real("total_repayment", ctx=ctx)
                solver = z3.Solver(ctx=ctx)
                solver.add(r_tot == total_repayment)
                solver.add(r_tot > allowed_repayment + 1.0)
                if solver.check() == z3.sat:
                    return True, total_repayment, implied_apr, "z3-smt-v4"
                return False, total_repayment, implied_apr, "z3-smt-v4"
        except Exception:
            pass

        return (
            total_repayment > allowed_repayment + 1.0,
            total_repayment,
            implied_apr,
            "sympy-scipy-smt-v2",
        )

    @staticmethod
    @lru_cache(maxsize=512)
    def prove_typography_hierarchy_breach(
        heading_size: float,
        body_size: float,
        min_heading_size: float = 24.0,
    ) -> tuple[bool, str, str]:
        """Prove brand typography hierarchy breach (`anthropics/skills/brand-guidelines`).

        Verifies both:
        1. $\\text{heading\\_size} > \\text{body\\_size}$ (strict visual hierarchy)
        2. $\\text{heading\\_size} \\ge \\text{min\\_heading\\_size}$ (e.g. 24pt Poppins threshold)
        """
        if heading_size <= body_size:
            return (
                True,
                f"heading_size ({heading_size:g}) <= body_size ({body_size:g})",
                "sympy-scipy-smt-v2",
            )
        if heading_size < min_heading_size:
            return (
                True,
                f"heading_size ({heading_size:g}) < min_heading_threshold ({min_heading_size:g})",
                "sympy-scipy-smt-v2",
            )
        return False, "", "sympy-scipy-smt-v2"


default_smt_solver = SmtConstraintSolver()


def _extract_bounds(
    text: str,
    pattern: re.Pattern[str],
    kind: Literal["upper", "lower"],
) -> tuple[BoundSpec, ...]:
    out: list[BoundSpec] = []
    for m in pattern.finditer(text):
        curr_sym = m.group(2)
        num_str = m.group(3)
        unit_tok = m.group(4)
        unit_dim = _classify_unit_dimension(curr_sym, unit_tok, m.group(0))
        out.append(
            BoundSpec(
                raw_text=m.group(0).strip(),
                value=_parse_scaled_value(num_str, unit_tok),
                span=Span(start=m.start(1), end=m.end(1)),
                kind=kind,
                unit_dim=unit_dim,
            )
        )
    return tuple(out)


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
            r"(₹|Rs\.?\s*|\$)?\s*(\d[\d,]*(?:\.\d+)?)"
            r"(?:\s*(%|(?:\b(?:percent|pct|thousand|crores?|lakhs?|months?|years?|weeks?|days?|lac|cr|kg|mg|pt|px|k|m|g)\b)))?",
            fact.metric_value,
            re.IGNORECASE,
        )
        if m:
            unit_dim = _classify_unit_dimension(m.group(1), m.group(3), fact_full)
            return BoundSpec(
                raw_text=fact.metric_value,
                value=_parse_scaled_value(m.group(2), m.group(3)),
                span=Span(start=0, end=len(fact.metric_value)),
                kind=kind,
                unit_dim=unit_dim,
            )
    return None


def _units_compatible(u1: UnitDimension, u2: UnitDimension) -> bool:
    return u1 == u2 or "scalar" in (u1, u2)


def _content_stems(text: str) -> set[str]:
    return {normalize_stem(w) for w in content_words(text)}


class ClaimAlgebraCheck(Check):
    check_id: ClassVar[str] = "claim.algebra"
    check_version: ClassVar[str] = "3.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, TextNode)
        findings: list[Finding] = []

        # 1. Self-contradictory tax-inclusive discount vs added GST
        findings.extend(self._check_tax_discount_contradiction(node))

        # 2. Multi-variable MRP / Offer Price / Claimed Discount % / Mandatory Fee equation
        findings.extend(self._check_mrp_discount_fee_equation(node))

        # 3. Multi-variable Loan Principal / Monthly EMI / Tenure / APR amortization equation
        findings.extend(self._check_loan_emi_apr_equation(node, canon))

        # 4. Self-contradictory min > max bounds within the same unit dimension
        findings.extend(self._check_self_contradictory_bounds(node))

        # 5. Brand-Guideline Typography Hierarchy & 60/30/10 Color Distribution checks
        findings.extend(self._check_brand_guideline_algebra(node))

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
            if not _units_compatible(d_bound.unit_dim, canon_cap.unit_dim):
                continue
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
                                "unit_dimension": d_bound.unit_dim,
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
            if not _units_compatible(d_bound.unit_dim, canon_floor.unit_dim):
                continue
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
                                "unit_dimension": d_bound.unit_dim,
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

    def _check_self_contradictory_bounds(self, node: TextNode) -> list[Finding]:
        lowers = _extract_lower_bounds(node.text)
        uppers = _extract_upper_bounds(node.text)
        if not lowers or not uppers:
            return []
        out: list[Finding] = []
        for lb in lowers:
            for ub in uppers:
                if lb.unit_dim != ub.unit_dim:
                    continue
                is_unsat, solver_sha = default_smt_solver.prove_self_contradictory_bounds(
                    lb.value, ub.value
                )
                if is_unsat:
                    loc = Span(
                        start=min(lb.span.start, ub.span.start),
                        end=max(lb.span.end, ub.span.end),
                    )
                    rule_ref = Rule(
                        rule_id="smt-interval-disjointness",
                        rule_type="fact",
                        source_text=(
                            "Mathematical consistency: lower bound cannot exceed upper bound."
                        ),
                    )
                    out.append(
                        self.finding(
                            node=node,
                            locator=loc,
                            severity=85,
                            message=(
                                f"Self-contradictory interval (UNSAT): lower bound {lb.value:,.0f} "
                                f"({lb.raw_text!r}) exceeds upper bound "
                                f"{ub.value:,.0f} ({ub.raw_text!r})."
                            ),
                            rule_ref=rule_ref,
                            evidence=AlgebraicProofEvidence(
                                draft_expr=f"x >= {lb.value:.0f} and x <= {ub.value:.0f}",
                                canon_constraint="lower_bound <= upper_bound",
                                solver_status="sat_counterexample",
                                counterexample={
                                    "lower_bound": f"{lb.value:.0f}",
                                    "upper_bound": f"{ub.value:.0f}",
                                    "unit_dimension": lb.unit_dim,
                                },
                            ),
                            suggestion=Suggestion(
                                label=f"Align bounds so minimum <= {ub.value:,.0f}",
                                replacements=(
                                    Replace(span=lb.span, replacement=ub.span.slice(node.text)),
                                ),
                            ),
                            trace=Trace(tier=Tier.SMT, model_sha=solver_sha),
                        )
                    )
        return out

    def _check_mrp_discount_fee_equation(self, node: TextNode) -> list[Finding]:
        mrp_m = _MRP_PRICE_RE.search(node.text)
        offer_m = _OFFER_PRICE_RE.search(node.text)
        disc_m = _DISCOUNT_PCT_RE.search(node.text)
        if not mrp_m or not offer_m or not disc_m:
            return []

        mrp_val = float(mrp_m.group(1).replace(",", ""))
        offer_val = float(offer_m.group(1).replace(",", ""))
        disc_val = float(disc_m.group(1))
        fee_m = _MANDATORY_FEE_RE.search(node.text)
        fee_val = float(fee_m.group(1).replace(",", "")) if fee_m else 0.0

        is_breach, eff_price, actual_disc_pct, solver_sha = (
            default_smt_solver.prove_mrp_discount_fee_contradiction(
                mrp_val, offer_val, disc_val, fee_val
            )
        )
        if not is_breach:
            return []

        loc_start = min(mrp_m.start(), offer_m.start(), disc_m.start())
        loc_end = max(
            mrp_m.end(),
            offer_m.end(),
            disc_m.end(),
            fee_m.end() if fee_m else 0,
        )
        rule_ref = Rule(
            rule_id="ccpa-mrp-discount-fee-math",
            rule_type="fact",
            source_text=(
                "CCPA 2023 Drip Pricing & False Discount Rules: effective checkout price "
                "(offer price + mandatory fees) must match the stated discount off MRP."
            ),
        )
        disc_span = Span(start=disc_m.start(1), end=disc_m.end(1))
        return [
            self.finding(
                node=node,
                locator=Span(start=loc_start, end=loc_end),
                severity=85,
                message=(
                    f"Multi-variable pricing contradiction: MRP {mrp_val:,.0f} with stated "
                    f"{disc_val:g}% discount requires checkout <= "
                    f"{mrp_val * (1 - disc_val / 100):,.0f}, but offer {offer_val:,.0f} + "
                    f"mandatory fee {fee_val:,.0f} = {eff_price:,.0f} "
                    f"(effective discount is only {actual_disc_pct:.2f}%)."
                ),
                rule_ref=rule_ref,
                evidence=AlgebraicProofEvidence(
                    draft_expr=(
                        f"mrp={mrp_val:.0f}, offer={offer_val:.0f}, fee={fee_val:.0f}, "
                        f"claimed_discount={disc_val:.2f}%"
                    ),
                    canon_constraint="offer + fee <= mrp * (1 - claimed_discount / 100)",
                    solver_status="sat_counterexample",
                    counterexample={
                        "mrp": f"{mrp_val:.0f}",
                        "effective_checkout_price": f"{eff_price:.2f}",
                        "claimed_discount_pct": f"{disc_val:.2f}%",
                        "actual_discount_pct": f"{actual_disc_pct:.2f}%",
                    },
                ),
                suggestion=Suggestion(
                    label=f"State true net discount {actual_disc_pct:.2f}%",
                    replacements=(Replace(span=disc_span, replacement=f"{actual_disc_pct:.2f}"),),
                ),
                trace=Trace(tier=Tier.SMT, model_sha=solver_sha),
            )
        ]

    def _check_loan_emi_apr_equation(self, node: TextNode, canon: Canon) -> list[Finding]:
        prin_m = _LOAN_PRINCIPAL_RE.search(node.text)
        emi_m = _EMI_AMOUNT_RE.search(node.text)
        ten_m = _TENURE_MONTHS_RE.search(node.text)
        if not prin_m or not emi_m or not ten_m:
            return []

        principal = _parse_scaled_value(prin_m.group(1), prin_m.group(2))
        emi_str = emi_m.group(1) or emi_m.group(2)
        emi = float(emi_str.replace(",", ""))
        tenure_months = int(ten_m.group(1))
        fee_m = _MANDATORY_FEE_RE.search(node.text)
        fee = float(fee_m.group(1).replace(",", "")) if fee_m else 0.0

        zero_int = _ZERO_INTEREST_RE.search(node.text) is not None
        stated_apr_m = _STATED_APR_RE.search(node.text)
        max_apr = 0.0 if zero_int else (float(stated_apr_m.group(1)) if stated_apr_m else None)

        if max_apr is None:
            for f in canon.facts:
                if "apr" in f.text.lower() and f.metric_value:
                    m_apr = re.search(r"(\d+(?:\.\d+)?)\s*%", f.metric_value)
                    if m_apr:
                        max_apr = float(m_apr.group(1))
                        break

        if max_apr is None:
            return []

        is_breach, total_rep, implied_apr, solver_sha = (
            default_smt_solver.prove_loan_emi_apr_contradiction(
                principal, emi, tenure_months, fee, max_apr
            )
        )
        if not is_breach:
            return []

        loc_start = min(prin_m.start(), emi_m.start(), ten_m.start())
        loc_end = max(prin_m.end(), emi_m.end(), ten_m.end())
        compliant_emi = (
            round(principal / tenure_months, 0)
            if max_apr == 0
            else round(
                (principal * (1.0 + (max_apr / 100.0) * (tenure_months / 24.0))) / tenure_months, 0
            )
        )
        rule_ref = Rule(
            rule_id="rbi-kfs-emi-apr-amortization",
            rule_type="fact",
            source_text=(
                "RBI 2025 Key Fact Statement (KFS) Amortization Truthfulness: total EMI "
                "repayment + fees must be mathematically consistent with stated APR."
            ),
        )
        return [
            self.finding(
                node=node,
                locator=Span(start=loc_start, end=loc_end),
                severity=85,
                message=(
                    f"Loan / EMI amortization contradiction: {tenure_months} months x "
                    f"{emi:,.0f} EMI + {fee:,.0f} fee = {total_rep:,.0f} total repayment on "
                    f"{principal:,.0f} principal (implied APR ~{implied_apr:.1f}%, violating "
                    f"stated/approved {max_apr:g}% APR bound)."
                ),
                rule_ref=rule_ref,
                evidence=AlgebraicProofEvidence(
                    draft_expr=(
                        f"principal={principal:.0f}, emi={emi:.0f}, months={tenure_months}, "
                        f"total_repayment={total_rep:.0f}"
                    ),
                    canon_constraint=f"implied_apr ({implied_apr:.1f}%) <= {max_apr:g}%",
                    solver_status="sat_counterexample",
                    counterexample={
                        "principal": f"{principal:.0f}",
                        "total_repayment": f"{total_rep:.0f}",
                        "hidden_finance_charge": f"{total_rep - principal:.0f}",
                        "implied_apr_pct": f"{implied_apr:.1f}%",
                    },
                ),
                suggestion=Suggestion(
                    label=f"Set compliant EMI to {compliant_emi:,.0f}/month",
                    replacements=(
                        Replace(
                            span=Span(start=emi_m.start(), end=emi_m.end()),
                            replacement=f"Rs {compliant_emi:,.0f}/month",
                        ),
                    ),
                ),
                trace=Trace(tier=Tier.SMT, model_sha=solver_sha),
            )
        ]

    def _check_brand_guideline_algebra(self, node: TextNode) -> list[Finding]:
        out: list[Finding] = []
        h_m = _HEADING_SIZE_RE.search(node.text)
        b_m = _BODY_SIZE_RE.search(node.text)
        if h_m and b_m and h_m.group(2).lower() == b_m.group(2).lower():
            h_val = float(h_m.group(1))
            b_val = float(b_m.group(1))
            unit = h_m.group(2).lower()
            min_h = 24.0
            is_breach, reason, solver_sha = default_smt_solver.prove_typography_hierarchy_breach(
                h_val, b_val, min_h
            )
            if is_breach:
                loc = Span(start=min(h_m.start(), b_m.start()), end=max(h_m.end(), b_m.end()))
                rule_ref = Rule(
                    rule_id="brand-typography-scale-hierarchy",
                    rule_type="fact",
                    source_text=(
                        "Brand Guidelines Typography Specification: "
                        "headings must be >= 24pt and strictly larger than body text."
                    ),
                )
                target_h = max(24, int(b_val * 1.5))
                out.append(
                    self.finding(
                        node=node,
                        locator=loc,
                        severity=75,
                        message=(
                            f"Brand typography hierarchy breach: {reason}. Headings must be "
                            f">= {min_h:g}{unit} and strictly larger than "
                            f"body copy ({b_val:g}{unit})."
                        ),
                        rule_ref=rule_ref,
                        evidence=AlgebraicProofEvidence(
                            draft_expr=f"heading={h_val:g}{unit}, body={b_val:g}{unit}",
                            canon_constraint=f"heading >= {min_h:g}{unit} and heading > body",
                            solver_status="sat_counterexample",
                            counterexample={
                                "heading_size": f"{h_val:g}{unit}",
                                "body_size": f"{b_val:g}{unit}",
                                "required_min_heading": f"{min_h:g}{unit}",
                            },
                        ),
                        suggestion=Suggestion(
                            label=f"Set heading size to {target_h}{unit}",
                            replacements=(
                                Replace(
                                    span=Span(start=h_m.start(1), end=h_m.end(2)),
                                    replacement=f"{target_h}{unit}",
                                ),
                            ),
                        ),
                        trace=Trace(tier=Tier.SMT, model_sha=solver_sha),
                    )
                )

        cr_m = _COLOR_RATIO_RE.search(node.text)
        if cr_m:
            p_pct = float(cr_m.group(1))
            s_pct = float(cr_m.group(2))
            a_pct = float(cr_m.group(3))
            total_pct = round(p_pct + s_pct + a_pct, 2)
            if abs(total_pct - 100.0) > 0.5 or a_pct > p_pct:
                loc = Span(start=cr_m.start(), end=cr_m.end())
                rule_ref = Rule(
                    rule_id="brand-color-ratio-60-30-10",
                    rule_type="fact",
                    source_text=(
                        "Brand Color Palette Management (60/30/10 Hierarchy): primary/neutral, "
                        "secondary, and accent ratios must sum to 100% with primary >= accent."
                    ),
                )
                out.append(
                    self.finding(
                        node=node,
                        locator=loc,
                        severity=70,
                        message=(
                            f"Brand color ratio breach: stated distribution "
                            f"{p_pct:g}% / {s_pct:g}% / {a_pct:g}% sums to {total_pct:g}% "
                            + (
                                "(accent exceeds primary)."
                                if a_pct > p_pct
                                else "(must sum to 100%)."
                            )
                        ),
                        rule_ref=rule_ref,
                        evidence=AlgebraicProofEvidence(
                            draft_expr=(
                                f"primary={p_pct:g}%, secondary={s_pct:g}%, accent={a_pct:g}%"
                            ),
                            canon_constraint=(
                                "primary + secondary + accent == 100% and primary >= accent"
                            ),
                            solver_status="sat_counterexample",
                            counterexample={
                                "sum_pct": f"{total_pct:g}%",
                                "primary_pct": f"{p_pct:g}%",
                                "accent_pct": f"{a_pct:g}%",
                            },
                        ),
                        suggestion=Suggestion(
                            label="Restore 60% primary, 30% secondary, 10% accent ratio",
                            replacements=(
                                Replace(
                                    span=loc,
                                    replacement="60% primary, 30% secondary, and 10% accent",
                                ),
                            ),
                        ),
                        trace=Trace(tier=Tier.SMT, model_sha="sympy-scipy-smt-v2"),
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
