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

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from canongate.domain.finding import Finding, SlotDiffEvidence


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
