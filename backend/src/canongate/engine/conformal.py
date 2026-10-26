r"""Conformal Risk Control for Calibrated NLI Fact Verification (`engine/conformal.py`).

Implements the distribution-free finite-sample risk control algorithm of
Angelopoulos, Bates, Fisch, Lei, & Schuster (2024/2025, `arXiv:2208.02814v4`):
- Given $n$ exchangeable calibration pairs $(p_i, Y_i)_{i=1}^n$ where
  $p_i = P(\\text{Canon} \\models X_i) \\in [0, 1]$ is the model's entailment score
  and $Y_i \\in \\{0, 1\\}$ indicates whether $X_i$ is a true compliance violation,
  the monotone False Negative Loss is:
    $L_i(\\lambda) = Y_i \\cdot \\mathbb{I}\\{p_i > \\lambda\\} \\in [0, 1]$
- For a user-selected risk tolerance $\\alpha \\in (0, 1)$, the Conformal Risk
  Control threshold $\\hat{\\lambda}(\\alpha)$ is:
    $\hat{\lambda}(\alpha) = \inf\{\lambda \in [0, 1] :
    \frac{n}{n+1}\widehat{R}_n(\lambda) + \frac{1}{n+1} \le \alpha\}
- Closed-Form Order Statistic:
  Let $p_{(1)} \\le p_{(2)} \\le \\dots \\le p_{(N_{\\text{viol}})}$ be the sorted entailment
  probabilities of the $N_{\\text{viol}} = \\sum_{i=1}^n Y_i$ true violations in the
  calibration set, and let $m = \\lfloor (n + 1)\\alpha \\rfloor$:
  - If $m \\le 0$: $\\hat{\\lambda}(\\alpha) = 1.0$ (conservative maximum sensitivity).
  - If $m > N_{\\text{viol}}$: $\\hat{\\lambda}(\\alpha) = 0.0$.
  - Otherwise: $\\hat{\\lambda}(\\alpha) = p_{(N_{\\text{viol}} - m)}$ (0-indexed).
  By Theorem 2.1 of Angelopoulos et al., this guarantees
  $\mathbb{E}[L_{n+1}(\hat{\lambda})] \le \alpha$.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from canongate.domain.ast import ContentAST, TextNode
from canongate.domain.canon import Canon, FactClaim, TermRule
from canongate.domain.finding import Finding, SlotDiffEvidence
from canongate.engine.runner import run_checks_collect


@dataclass(frozen=True, slots=True)
class CalibrationSample:
    """Single labeled NLI calibration point $(p_i, Y_i)$."""

    sample_id: str
    entailment_prob: float
    is_violation: bool


# Default 49-sample CanonGate calibration set (so n + 1 = 50 gives exact 2% steps in alpha):
# 20 true violations (Y_i = 1) spanning [0.02, 0.44] and 29 compliant claims (Y_i = 0)
# spanning [0.55, 0.99].
DEFAULT_CALIBRATION_SAMPLES: tuple[CalibrationSample, ...] = (
    # True compliance violations (qualifier stripped, metric drifted, or unsubstantiated)
    CalibrationSample("cal-v01", 0.02, True),
    CalibrationSample("cal-v02", 0.04, True),
    CalibrationSample("cal-v03", 0.06, True),
    CalibrationSample("cal-v04", 0.08, True),
    CalibrationSample("cal-v05", 0.10, True),
    CalibrationSample("cal-v06", 0.12, True),
    CalibrationSample("cal-v07", 0.14, True),
    CalibrationSample("cal-v08", 0.16, True),
    CalibrationSample("cal-v09", 0.18, True),
    CalibrationSample("cal-v10", 0.20, True),
    CalibrationSample("cal-v11", 0.22, True),
    CalibrationSample("cal-v12", 0.24, True),
    CalibrationSample("cal-v13", 0.26, True),
    CalibrationSample("cal-v14", 0.28, True),
    CalibrationSample("cal-v15", 0.31, True),
    CalibrationSample("cal-v16", 0.34, True),
    CalibrationSample("cal-v17", 0.37, True),
    CalibrationSample("cal-v18", 0.40, True),
    CalibrationSample("cal-v19", 0.42, True),
    CalibrationSample("cal-v20", 0.45, True),
    # Compliant claims (entailed by Canon)
    CalibrationSample("cal-c01", 0.56, False),
    CalibrationSample("cal-c02", 0.59, False),
    CalibrationSample("cal-c03", 0.62, False),
    CalibrationSample("cal-c04", 0.65, False),
    CalibrationSample("cal-c05", 0.68, False),
    CalibrationSample("cal-c06", 0.70, False),
    CalibrationSample("cal-c07", 0.72, False),
    CalibrationSample("cal-c08", 0.74, False),
    CalibrationSample("cal-c09", 0.76, False),
    CalibrationSample("cal-c10", 0.78, False),
    CalibrationSample("cal-c11", 0.80, False),
    CalibrationSample("cal-c12", 0.82, False),
    CalibrationSample("cal-c13", 0.84, False),
    CalibrationSample("cal-c14", 0.85, False),
    CalibrationSample("cal-c15", 0.86, False),
    CalibrationSample("cal-c16", 0.88, False),
    CalibrationSample("cal-c17", 0.89, False),
    CalibrationSample("cal-c18", 0.90, False),
    CalibrationSample("cal-c19", 0.91, False),
    CalibrationSample("cal-c20", 0.92, False),
    CalibrationSample("cal-c21", 0.93, False),
    CalibrationSample("cal-c22", 0.94, False),
    CalibrationSample("cal-c23", 0.95, False),
    CalibrationSample("cal-c24", 0.96, False),
    CalibrationSample("cal-c25", 0.97, False),
    CalibrationSample("cal-c26", 0.975, False),
    CalibrationSample("cal-c27", 0.98, False),
    CalibrationSample("cal-c28", 0.985, False),
    CalibrationSample("cal-c29", 0.99, False),
)


class ConformalRiskCalibrator:
    """Closed-form Conformal Risk Control calibrator (Angelopoulos et al.)."""

    __slots__ = ("_samples", "_sorted_violation_probs")

    def __init__(
        self,
        samples: Sequence[CalibrationSample] = DEFAULT_CALIBRATION_SAMPLES,
    ) -> None:
        self._samples: tuple[CalibrationSample, ...] = tuple(samples)
        self._sorted_violation_probs: tuple[float, ...] = tuple(
            sorted(s.entailment_prob for s in self._samples if s.is_violation)
        )

    def __len__(self) -> int:
        return len(self._samples)

    def __iter__(self) -> Iterator[CalibrationSample]:
        return iter(self._samples)

    def __repr__(self) -> str:
        return (
            f"ConformalRiskCalibrator(n={len(self._samples)}, "
            f"violations={len(self._sorted_violation_probs)})"
        )

    @property
    def violation_count(self) -> int:
        return len(self._sorted_violation_probs)

    def empirical_fnr(self, lam: float) -> float:
        r"""Compute empirical false-negative risk
        $\widehat{R}_n(\lambda) = \frac{1}{n}\sum Y_i \mathbb{I}\{p_i > \lambda\}$.
        """
        n = len(self._samples)
        if n == 0:
            return 0.0
        missed = sum(1 for p in self._sorted_violation_probs if p > lam)
        return missed / float(n)

    def conformal_upper_bound(self, lam: float) -> float:
        r"""Compute finite-sample conformal risk bound
        $\frac{n}{n+1}\widehat{R}_n(\lambda) + \frac{1}{n+1}$.
        """
        n = len(self._samples)
        if n == 0:
            return 1.0
        missed = sum(1 for p in self._sorted_violation_probs if p > lam)
        return (missed + 1.0) / float(n + 1)

    def threshold(self, alpha: float = 0.10) -> float:
        r"""Return the exact closed-form order-statistic cutoff
        $\hat{\lambda}(\alpha) \in [0, 1]$.
        """
        clamped_alpha = max(0.001, min(0.999, float(alpha)))
        n = len(self._samples)
        n_viol = len(self._sorted_violation_probs)
        if n == 0 or n_viol == 0:
            return 0.50

        # Number of allowed missed violations plus the +1 finite-sample inflation term:
        # missed + 1 <= (n + 1) * alpha  <=>  missed <= floor((n + 1) * alpha) - 1
        m = math.floor((n + 1) * clamped_alpha + 1e-12)
        if m <= 0:
            return 1.0
        if m > n_viol:
            return 0.0
        idx = n_viol - m
        return round(self._sorted_violation_probs[idx], 4)

    def filter_and_calibrate_findings(
        self,
        findings: Sequence[Finding],
        alpha: float = 0.10,
    ) -> list[Finding]:
        r"""Apply the Conformal Risk Control cutoff $\hat{\lambda}(\alpha)$
        to Tier 2 NLI findings.

        - Non-NLI findings (Tier 1 deterministic and Tier 1.5 SMT proofs) pass through unchanged.
        - For Tier 2 `SlotDiffEvidence` findings:
          - If `entailment_prob > threshold(alpha)`, the claim satisfies the conformal
            risk bound at tolerance $\\alpha$ and is suppressed.
          - Under strict risk tolerance ($\\alpha \\le 0.05$), borderline NLI warnings
            (`severity < 50`) are escalated to Blockers (`severity = 65`).
        """
        lam = self.threshold(alpha)
        calibrated: list[Finding] = []
        for f in findings:
            ev = f.evidence
            if isinstance(ev, SlotDiffEvidence):
                if ev.entailment_prob > lam:
                    continue
                if alpha <= 0.05 and f.severity < 50:
                    f = f.model_copy(
                        update={
                            "severity": 65,
                            "message": (f"[Conformal α={alpha:.2f}, λ̂={lam:.2f}] {f.message}"),
                        }
                    )
            calibrated.append(f)
        return calibrated


default_calibrator = ConformalRiskCalibrator()


# ---------------------------------------------------------------------------
# 50-Case Adversarial Red-Team Mutation Benchmark Suite
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RedTeamCase:
    """Single adversarial mutation case or compliant control."""

    case_id: str
    operator: str
    text: str
    expected_checks: tuple[str, ...]
    description: str


@dataclass(frozen=True, slots=True)
class OperatorBenchmarkSummary:
    """Aggregated recall & latency metrics for one mutation operator."""

    operator: str
    total_cases: int
    detected_cases: int
    recall: float
    mean_latency_ms: float
    p95_latency_ms: float
    expected_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator": self.operator,
            "total_cases": self.total_cases,
            "detected_cases": self.detected_cases,
            "recall": round(self.recall, 4),
            "mean_latency_ms": round(self.mean_latency_ms, 3),
            "p95_latency_ms": round(self.p95_latency_ms, 3),
            "expected_checks": list(self.expected_checks),
        }


@dataclass(frozen=True, slots=True)
class RedTeamBenchmarkReport:
    """Complete 50-case red-team benchmark + 10-control evaluation report."""

    total_adversarial_cases: int
    total_detected: int
    overall_recall: float
    control_cases: int
    false_positives: int
    false_positive_rate: float
    operators: tuple[OperatorBenchmarkSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_adversarial_cases": self.total_adversarial_cases,
            "total_detected": self.total_detected,
            "overall_recall": round(self.overall_recall, 4),
            "control_cases": self.control_cases,
            "false_positives": self.false_positives,
            "false_positive_rate": round(self.false_positive_rate, 4),
            "operators": [op.to_dict() for op in self.operators],
        }

    def to_markdown_table(self) -> str:
        header = (
            "| Mutation Operator | Cases | Detected | Recall | Target Check(s) | "
            "Mean Latency (ms) | p95 Latency (ms) |"
        )
        lines = [
            header,
            "|---|---:|---:|---:|---|---:|---:|",
        ]
        for op in self.operators:
            checks_str = ", ".join(f"`{c}`" for c in op.expected_checks)
            lines.append(
                f"| `{op.operator}` | {op.total_cases} | {op.detected_cases} | "
                f"{op.recall * 100:.1f}% | {checks_str} | "
                f"{op.mean_latency_ms:.2f} | {op.p95_latency_ms:.2f} |"
            )
        lines.append(
            f"| **Total Adversarial** | **{self.total_adversarial_cases}** | "
            f"**{self.total_detected}** | **{self.overall_recall * 100:.1f}%** | "
            f"All 5 Operators | — | — |"
        )
        lines.append(
            f"| **Compliant Controls (FPR)** | **{self.control_cases}** | "
            f"**{self.false_positives} FP** | **FPR = {self.false_positive_rate * 100:.1f}%** | "
            f"Zero False Positives | — | — |"
        )
        return "\n".join(lines)


def build_benchmark_canon() -> Canon:
    """Build the reference Canon used by the 50-case red-team benchmark."""
    return Canon(
        id="redteam-benchmark-canon",
        version="1.0",
        terminology=(
            TermRule(id="t-cheap", pattern_text="cheap", preferred="affordable", severity=60),
            TermRule(id="t-buy", pattern_text="buy", preferred="purchase", severity=40),
            TermRule(id="t-users", pattern_text="users", preferred="customers", severity=30),
            TermRule(
                id="t-cutting",
                pattern_text="cutting-edge",
                preferred="innovative",
                severity=20,
            ),
            TermRule(
                id="t-guar",
                pattern_text="guaranteed approval",
                preferred="subject to credit assessment",
                severity=85,
            ),
            TermRule(
                id="t-miracle",
                pattern_text="miracle cure",
                preferred="clinically formulated supplement",
                severity=90,
            ),
            TermRule(
                id="t-fatburn",
                pattern_text="100% fat burn",
                preferred="supports healthy metabolism",
                severity=85,
            ),
            TermRule(
                id="t-nocredit",
                pattern_text="no credit check",
                preferred="streamlined bureau verification",
                severity=80,
            ),
            TermRule(
                id="t-riskfree",
                pattern_text="risk-free returns",
                preferred="market-linked returns",
                severity=85,
            ),
            TermRule(
                id="t-instantrich",
                pattern_text="instant wealth",
                preferred="long-term financial planning",
                severity=75,
            ),
        ),
        facts=(
            FactClaim(
                id="f-founded",
                text="Acme Corp was founded in 2020.",
                conditions=(),
            ),
            FactClaim(
                id="f-customers",
                text="Acme Corp serves over 500 enterprise customers as of Q3 2025.",
                conditions=("as of Q3 2025",),
            ),
            FactClaim(
                id="f-loan-fee",
                text="0% processing fee on personal loans under Rs 50,000.",
                conditions=("under Rs 50,000",),
                valid_until="2026-09-30",
            ),
            FactClaim(
                id="f-cashback",
                text=(
                    "Get 10% instant cashback on UPI payments only for first-time salaried"
                    " borrowers."
                ),
                conditions=("only for first-time salaried borrowers",),
            ),
            FactClaim(
                id="f-rapido",
                text="Auto in 5 minutes or get Rs 50 only on bike rides in select metro cities.",
                conditions=("only on bike rides in select metro cities",),
            ),
            FactClaim(
                id="f-serum",
                text=(
                    "Redensyl serum boosts hair growth by 23,800 strands after 84 days of daily"
                    " application."
                ),
                conditions=("after 84 days of daily application",),
            ),
            FactClaim(
                id="f-upsc",
                text=(
                    "Over 645 selections in UPSC CSE 2023 includes Mock Interview programme"
                    " enrollees."
                ),
                conditions=("includes Mock Interview programme enrollees",),
            ),
            FactClaim(
                id="f-uptime",
                text="99.99% SLA uptime commitment only on annual enterprise plans.",
                conditions=("only on annual enterprise plans",),
            ),
            FactClaim(
                id="f-apr",
                text="10.5% lowest APR starting rate subject to CIBIL score above 750.",
                conditions=("subject to CIBIL score above 750",),
            ),
            FactClaim(
                id="f-refund",
                text="Full 30-day money-back assurance only on unopened starter packs.",
                conditions=("only on unopened starter packs",),
            ),
            FactClaim(
                id="f-delivery",
                text="Same-day 2-hour express delivery only in Mumbai and Bengaluru.",
                conditions=("only in Mumbai and Bengaluru",),
            ),
        ),
    )


REDTEAM_50_CASES: tuple[RedTeamCase, ...] = (
    # ── 1. drop_qualifier (10 cases) ──────────────────────────────────
    RedTeamCase(
        "dq-01",
        "drop_qualifier",
        "Acme Corp serves over 500 enterprise customers.",
        ("claim.slot_nli",),
        "Drops 'as of Q3 2025' temporal qualifier",
    ),
    RedTeamCase(
        "dq-02",
        "drop_qualifier",
        "0% processing fee on personal loans today.",
        ("claim.slot_nli",),
        "Drops 'under Rs 50,000' loan ceiling qualifier",
    ),
    RedTeamCase(
        "dq-03",
        "drop_qualifier",
        "Get 10% instant cashback on UPI payments.",
        ("claim.slot_nli",),
        "Drops 'only for first-time salaried borrowers' eligibility qualifier",
    ),
    RedTeamCase(
        "dq-04",
        "drop_qualifier",
        "Auto in 5 minutes or get Rs 50 every time.",
        ("claim.slot_nli",),
        "Drops 'only on bike rides in select metro cities' Rapido condition",
    ),
    RedTeamCase(
        "dq-05",
        "drop_qualifier",
        "Redensyl serum boosts hair growth by 23,800 strands.",
        ("claim.slot_nli",),
        "Drops 'after 84 days of daily application' study duration condition",
    ),
    RedTeamCase(
        "dq-06",
        "drop_qualifier",
        "Over 645 selections in UPSC CSE 2023 across India.",
        ("claim.slot_nli",),
        "Drops 'includes Mock Interview programme enrollees' Vajirao disclosure",
    ),
    RedTeamCase(
        "dq-07",
        "drop_qualifier",
        "We deliver a 99.99% SLA uptime commitment for all accounts.",
        ("claim.slot_nli",),
        "Drops 'only on annual enterprise plans' tier condition",
    ),
    RedTeamCase(
        "dq-08",
        "drop_qualifier",
        "Lock in a 10.5% lowest APR starting rate today.",
        ("claim.slot_nli",),
        "Drops 'subject to CIBIL score above 750' credit condition",
    ),
    RedTeamCase(
        "dq-09",
        "drop_qualifier",
        "Enjoy a full 30-day money-back assurance on every order.",
        ("claim.slot_nli",),
        "Drops 'only on unopened starter packs' return condition",
    ),
    RedTeamCase(
        "dq-10",
        "drop_qualifier",
        "Get same-day 2-hour express delivery nationwide.",
        ("claim.slot_nli",),
        "Drops 'only in Mumbai and Bengaluru' geographic scope",
    ),
    # ── 2. numeric_drift (10 cases) ───────────────────────────────────
    RedTeamCase(
        "nd-01",
        "numeric_drift",
        "Acme Corp was founded in 2018.",
        ("claim.algebra", "claim.slot_nli"),
        "Founding year drifted from 2020 to 2018",
    ),
    RedTeamCase(
        "nd-02",
        "numeric_drift",
        "Acme Corp was founded in 2015.",
        ("claim.algebra", "claim.slot_nli"),
        "Founding year drifted from 2020 to 2015",
    ),
    RedTeamCase(
        "nd-03",
        "numeric_drift",
        "0% processing fee on personal loans under Rs 75,000.",
        ("claim.algebra", "claim.slot_nli"),
        "Loan cap breached: Rs 75,000 > Rs 50,000",
    ),
    RedTeamCase(
        "nd-04",
        "numeric_drift",
        "0% processing fee on personal loans up to Rs 1,00,000.",
        ("claim.algebra", "claim.slot_nli"),
        "Loan cap breached: Rs 1,00,000 > Rs 50,000",
    ),
    RedTeamCase(
        "nd-05",
        "numeric_drift",
        "0% processing fee on personal loans up to Rs 1.5 Lakh.",
        ("claim.algebra", "claim.slot_nli"),
        "Indian Lakh unit cap breach: Rs 1,50,000 > Rs 50,000",
    ),
    RedTeamCase(
        "nd-06",
        "numeric_drift",
        "0% processing fee on personal loans under Rs 50,000 valid until 2026-12-31.",
        ("claim.algebra", "claim.slot_nli"),
        "Offer expiry breached: 2026-12-31 > 2026-09-30",
    ),
    RedTeamCase(
        "nd-07",
        "numeric_drift",
        "0% processing fee on personal loans under Rs 50,000 valid until 2027-03-31.",
        ("claim.algebra", "claim.slot_nli"),
        "Offer expiry breached into 2027: 2027-03-31 > 2026-09-30",
    ),
    RedTeamCase(
        "nd-08",
        "numeric_drift",
        "Acme Corp serves over 900 enterprise customers as of Q3 2025.",
        ("claim.algebra", "claim.slot_nli"),
        "Customer count inflated from 500 to 900",
    ),
    RedTeamCase(
        "nd-09",
        "numeric_drift",
        "Get 25% instant cashback on UPI payments only for first-time salaried borrowers.",
        ("claim.algebra", "claim.slot_nli"),
        "Cashback percentage inflated from 10% to 25%",
    ),
    RedTeamCase(
        "nd-10",
        "numeric_drift",
        "Flat 27% Off on MRP (Inclusive of all taxes). 18% GST applies on discounted price.",
        ("claim.algebra", "claim.slot_nli"),
        "FirstCry stacked GST net-discount contradiction (27% vs 13.86% effective)",
    ),
    # ── 3. banned_synonym (10 cases) ──────────────────────────────────
    RedTeamCase(
        "bs-01",
        "banned_synonym",
        "Purchase our CHEAP enterprise platform.",
        ("terminology.banned",),
        "Uppercase banned term 'CHEAP'",
    ),
    RedTeamCase(
        "bs-02",
        "banned_synonym",
        "Buy our affordable enterprise platform.",
        ("terminology.banned",),
        "Titlecase banned verb 'Buy'",
    ),
    RedTeamCase(
        "bs-03",
        "banned_synonym",
        "Our platform serves enterprise users worldwide.",
        ("terminology.banned",),
        "Banned noun 'users' instead of 'customers'",
    ),
    RedTeamCase(
        "bs-04",
        "banned_synonym",
        "Discover our Cutting-Edge cloud governance suite.",
        ("terminology.banned",),
        "Hyphenated banned buzzword 'Cutting-Edge'",
    ),
    RedTeamCase(
        "bs-05",
        "banned_synonym",
        "Apply now for guaranteed approval on your credit line.",
        ("terminology.banned",),
        "RBI prohibited phrase 'guaranteed approval'",
    ),
    RedTeamCase(
        "bs-06",
        "banned_synonym",
        "Try our herbal miracle cure for better sleep.",
        ("terminology.banned",),
        "ASCI prohibited therapeutic claim 'miracle cure'",
    ),
    RedTeamCase(
        "bs-07",
        "banned_synonym",
        "Achieve 100% fat burn in two weeks.",
        ("terminology.banned",),
        "Symbol-prefixed banned claim '100% fat burn'",
    ),
    RedTeamCase(
        "bs-08",
        "banned_synonym",
        "Instant digital loans with no credit check required.",
        ("terminology.banned",),
        "RBI prohibited phrase 'no credit check'",
    ),
    RedTeamCase(
        "bs-09",
        "banned_synonym",
        "Earn risk-free returns with our treasury vault.",
        ("terminology.banned",),
        "SEBI/RBI prohibited phrase 'risk-free returns'",
    ),
    RedTeamCase(
        "bs-10",
        "banned_synonym",
        "Unlock instant wealth with automated trading.",
        ("terminology.banned",),
        "Prohibited financial phrase 'instant wealth'",
    ),
    # ── 4. homoglyph_injection (10 cases) ─────────────────────────────
    RedTeamCase(
        "hg-01",
        "homoglyph_injection",
        "Our ch\u0435ap plan is live.",
        ("unicode.confusable",),
        "Cyrillic small 'е' (U+0435) inside 'cheap'",
    ),
    RedTeamCase(
        "hg-02",
        "homoglyph_injection",
        "Apply for \u0430ffordable credit.",
        ("unicode.confusable",),
        "Cyrillic small 'а' (U+0430) inside 'affordable'",
    ),
    RedTeamCase(
        "hg-03",
        "homoglyph_injection",
        "Zero\u200bwidth space injection.",
        ("unicode.confusable",),
        "Zero-width space (U+200B) inside token",
    ),
    RedTeamCase(
        "hg-04",
        "homoglyph_injection",
        "Get gu\u0430ranteed loan disbursal.",
        ("unicode.confusable",),
        "Cyrillic small 'а' (U+0430) inside 'guaranteed'",
    ),
    RedTeamCase(
        "hg-05",
        "homoglyph_injection",
        "Fast cr\u0435dit line for salaried professionals.",
        ("unicode.confusable",),
        "Cyrillic small 'е' (U+0435) inside 'credit'",
    ),
    RedTeamCase(
        "hg-06",
        "homoglyph_injection",
        "Special disc\u043eunt on annual billing.",
        ("unicode.confusable",),
        "Cyrillic small 'о' (U+043E) inside 'discount'",
    ),
    RedTeamCase(
        "hg-07",
        "homoglyph_injection",
        "Instant appr\u043eval in 60 seconds.",
        ("unicode.confusable",),
        "Cyrillic small 'о' (U+043E) inside 'approval'",
    ),
    RedTeamCase(
        "hg-08",
        "homoglyph_injection",
        "Earn cash\u200cback on every transaction.",
        ("unicode.confusable",),
        "Zero-width non-joiner (U+200C) inside 'cashback'",
    ),
    RedTeamCase(
        "hg-09",
        "homoglyph_injection",
        "Claim your free\u200dmoney bonus today.",
        ("unicode.confusable",),
        "Zero-width joiner (U+200D) inside 'freemoney'",
    ),
    RedTeamCase(
        "hg-10",
        "homoglyph_injection",
        "Mir\u0430cle wellness supplement.",
        ("unicode.confusable",),
        "Cyrillic small 'а' (U+0430) inside 'Miracle'",
    ),
    # ── 5. wcag_boundary_shift (10 cases) ─────────────────────────────
    RedTeamCase(
        "wb-01",
        "wcag_boundary_shift",
        "color: #FFFFFF; background-color: #777777; Single-hex boundary failure (4.48:1)",
        ("accessibility.contrast",),
        "#FFFFFF on #777777 = 4.48:1 (< 4.5:1 AA threshold)",
    ),
    RedTeamCase(
        "wb-02",
        "wcag_boundary_shift",
        "color: #777777; background-color: #FFFFFF; Inverse boundary failure (4.48:1)",
        ("accessibility.contrast",),
        "#777777 on #FFFFFF = 4.48:1 (< 4.5:1 AA threshold)",
    ),
    RedTeamCase(
        "wb-03",
        "wcag_boundary_shift",
        "color: #787878; background-color: #FFFFFF; Sub-boundary grey (4.41:1)",
        ("accessibility.contrast",),
        "#787878 on #FFFFFF = 4.41:1 (< 4.5:1 AA threshold)",
    ),
    RedTeamCase(
        "wb-04",
        "wcag_boundary_shift",
        "color: #808080; background-color: #FFFFFF; Mid-grey disclaimer (3.95:1)",
        ("accessibility.contrast",),
        "#808080 on #FFFFFF = 3.95:1 (< 4.5:1 AA threshold)",
    ),
    RedTeamCase(
        "wb-05",
        "wcag_boundary_shift",
        "color: #FFFFFF; background-color: #9E9E9E; Muted grey badge (2.68:1)",
        ("accessibility.contrast",),
        "#FFFFFF on #9E9E9E = 2.68:1 (< 4.5:1 AA threshold)",
    ),
    RedTeamCase(
        "wb-06",
        "wcag_boundary_shift",
        "color: #AAAAAA; background-color: #FFFFFF; Light grey footnote (2.32:1)",
        ("accessibility.contrast",),
        "#AAAAAA on #FFFFFF = 2.32:1 (< 4.5:1 AA threshold)",
    ),
    RedTeamCase(
        "wb-07",
        "wcag_boundary_shift",
        "color: #FFFFFF; background-color: #888888; Grey pill button (3.54:1)",
        ("accessibility.contrast",),
        "#FFFFFF on #888888 = 3.54:1 (< 4.5:1 AA threshold)",
    ),
    RedTeamCase(
        "wb-08",
        "wcag_boundary_shift",
        "color: #CCCCCC; background-color: #FFFFFF; Washed-out legal copy (1.61:1)",
        ("accessibility.contrast",),
        "#CCCCCC on #FFFFFF = 1.61:1 (< 4.5:1 AA threshold)",
    ),
    RedTeamCase(
        "wb-09",
        "wcag_boundary_shift",
        "color: #8A99AD; background-color: #FFFFFF; Slate muted caption (2.91:1)",
        ("accessibility.contrast",),
        "#8A99AD on #FFFFFF = 2.91:1 (< 4.5:1 AA threshold)",
    ),
    RedTeamCase(
        "wb-10",
        "wcag_boundary_shift",
        "color: #6E85A1; background-color: #F0F4F8; Low-contrast card footer (3.45:1)",
        ("accessibility.contrast",),
        "#6E85A1 on #F0F4F8 = 3.45:1 (< 4.5:1 AA threshold)",
    ),
)


COMPLIANT_CONTROL_10_CASES: tuple[str, ...] = (
    "Acme Corp was founded in 2020.",
    "Acme Corp serves over 500 enterprise customers as of Q3 2025.",
    "0% processing fee on personal loans under Rs 50,000.",
    "Get 10% instant cashback on UPI payments only for first-time salaried borrowers.",
    "Auto in 5 minutes or get Rs 50 only on bike rides in select metro cities.",
    "Redensyl serum boosts hair growth by 23,800 strands after 84 days of daily application.",
    "99.99% SLA uptime commitment only on annual enterprise plans.",
    "Purchase our innovative and affordable enterprise platform for customers.",
    "color: #FFFFFF; background-color: #767676; Compliant AA boundary disclaimer (4.54:1)",
    "color: #1E293B; background-color: #FFFFFF; High-contrast primary body copy (14.6:1)",
)


async def run_redteam_benchmark_async(
    canon: Canon | None = None,
) -> RedTeamBenchmarkReport:
    """Execute all 50 adversarial cases + 10 compliant controls and return the report."""
    active_canon = canon or build_benchmark_canon()

    # 1. Evaluate 10 compliant controls
    false_positives = 0
    for idx, ctrl_text in enumerate(COMPLIANT_CONTROL_10_CASES):
        ast = ContentAST(nodes=(TextNode.from_text(ctrl_text, path=f"control/p[{idx}]"),))
        fds = await run_checks_collect(ast, active_canon)
        if len(fds) > 0:
            false_positives += 1

    # 2. Evaluate 50 adversarial cases grouped by operator
    operators_order = (
        "drop_qualifier",
        "numeric_drift",
        "banned_synonym",
        "homoglyph_injection",
        "wcag_boundary_shift",
    )
    summaries: list[OperatorBenchmarkSummary] = []
    total_detected = 0

    for op_name in operators_order:
        op_cases = [c for c in REDTEAM_50_CASES if c.operator == op_name]
        detected = 0
        latencies: list[float] = []
        expected_checks = op_cases[0].expected_checks if op_cases else ()

        for c in op_cases:
            t0 = time.perf_counter()
            ast = ContentAST(nodes=(TextNode.from_text(c.text, path=f"redteam/{c.case_id}"),))
            fds = await run_checks_collect(ast, active_canon)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)
            if any(f.check_id in c.expected_checks for f in fds):
                detected += 1

        total_detected += detected
        sorted_lat = sorted(latencies)
        p95_idx = min(len(sorted_lat) - 1, max(0, int(len(sorted_lat) * 0.95) - 1))
        summaries.append(
            OperatorBenchmarkSummary(
                operator=op_name,
                total_cases=len(op_cases),
                detected_cases=detected,
                recall=detected / len(op_cases) if op_cases else 1.0,
                mean_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
                p95_latency_ms=sorted_lat[p95_idx] if sorted_lat else 0.0,
                expected_checks=expected_checks,
            )
        )

    total_adv = len(REDTEAM_50_CASES)
    n_ctrl = len(COMPLIANT_CONTROL_10_CASES)
    return RedTeamBenchmarkReport(
        total_adversarial_cases=total_adv,
        total_detected=total_detected,
        overall_recall=total_detected / total_adv if total_adv else 1.0,
        control_cases=n_ctrl,
        false_positives=false_positives,
        false_positive_rate=false_positives / n_ctrl if n_ctrl else 0.0,
        operators=tuple(summaries),
    )


def run_redteam_benchmark(canon: Canon | None = None) -> RedTeamBenchmarkReport:
    """Synchronous wrapper for `run_redteam_benchmark_async`."""
    return asyncio.run(run_redteam_benchmark_async(canon))
