"""Guideline Friction Analytics & Vectorized Krippendorff's Alpha.

Licensing note:
Upstream `pln-fing-udelar/fast-krippendorff` is licensed under GPL-3.0, which
conflicts with CanonGate's permissive MIT/Apache-2.0/BSD-3 policy. This module
implements vectorized O(N * V^2) Krippendorff's alpha coincidence matrix
computation and Empirical Bayes Beta-Binomial rule friction natively in NumPy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class RuleFrictionReport:
    rule_id: str
    total_flags: int
    overrides_and_disputes: int
    raw_friction: float
    posterior_friction: float
    needs_canon_revision: bool

    def __bool__(self) -> bool:
        """Return True when this rule exceeds the friction revision threshold."""
        return self.needs_canon_revision


def compute_rule_friction(
    rule_id: str,
    total_flags: int,
    overrides_and_disputes: int,
    *,
    alpha_0: float = 1.0,
    beta_0: float = 4.0,
    revision_threshold: float = 0.40,
) -> RuleFrictionReport:
    """Compute Empirical Bayes Beta-Binomial posterior override friction for a rule.

    Shrinks noisy low-sample override rates toward the prior mean
    alpha_0 / (alpha_0 + beta_0) = 0.20 so a single overridden flag (1/1)
    does not falsely trigger a Canon v1.1 revision alert.
    """
    if total_flags < 0 or overrides_and_disputes < 0:
        raise ValueError("total_flags and overrides_and_disputes must be non-negative")
    if overrides_and_disputes > total_flags:
        raise ValueError(
            f"overrides_and_disputes ({overrides_and_disputes}) "
            f"cannot exceed total_flags ({total_flags})"
        )

    raw = overrides_and_disputes / total_flags if total_flags > 0 else 0.0
    posterior = (alpha_0 + overrides_and_disputes) / (alpha_0 + beta_0 + total_flags)
    return RuleFrictionReport(
        rule_id=rule_id,
        total_flags=total_flags,
        overrides_and_disputes=overrides_and_disputes,
        raw_friction=round(raw, 4),
        posterior_friction=round(posterior, 4),
        needs_canon_revision=posterior > revision_threshold and total_flags >= 3,
    )


def krippendorff_alpha(
    reliability_data: np.ndarray | list[list[float | None]],
    level_of_measurement: Literal["nominal", "interval"] = "nominal",
) -> float:
    """Compute Krippendorff's alpha inter-reviewer agreement in O(N * V^2) time.

    Args:
        reliability_data: 2D array-like of shape (M_reviewers, N_units) where
            missing ratings are represented as `np.nan` or `None`.
        level_of_measurement: `"nominal"` (discrete categories) or `"interval"`.

    Returns:
        Krippendorff's alpha coefficient in [-1.0, 1.0]. Returns 1.0 when
        all pairable ratings agree completely.
    """
    data = np.asarray(reliability_data, dtype=np.float64)
    if data.ndim != 2:
        raise ValueError("reliability_data must be a 2D array of shape (M_coders, N_units)")

    valid_mask = ~np.isnan(data)
    m_u = valid_mask.sum(axis=0)  # Number of raters per unit (shape: N,)
    pairable = m_u >= 2
    if not np.any(pairable):
        return 1.0

    data = data[:, pairable]
    valid_pairable = valid_mask[:, pairable]
    m_u = m_u[pairable]

    values, inv_indices = np.unique(data[valid_pairable], return_inverse=True)
    v_count = len(values)
    if v_count <= 1:
        return 1.0

    # Vectorized value-by-unit count matrix n_vu of shape (V, N_pairable) via np.add.at
    n_pairable = data.shape[1]
    n_vu = np.zeros((v_count, n_pairable), dtype=np.float64)
    _, col_indices = np.nonzero(valid_pairable)
    np.add.at(n_vu, (inv_indices, col_indices), 1.0)

    # Observed coincidence matrix O of shape (V, V):
    # O_{v, v'} = sum_u [ n_{uv} * (n_{uv'} - I(v == v')) / (m_u - 1) ]
    weights = 1.0 / (m_u - 1.0)
    o_matrix = (n_vu * weights) @ n_vu.T
    diag_adjust = (n_vu * weights).sum(axis=1)
    np.fill_diagonal(o_matrix, np.diag(o_matrix) - diag_adjust)

    n_v = o_matrix.sum(axis=1)
    n_total = float(n_v.sum())
    if n_total <= 1.0:
        return 1.0

    # Expected coincidence matrix E of shape (V, V)
    e_matrix = np.outer(n_v, n_v) / (n_total - 1.0)
    np.fill_diagonal(e_matrix, n_v * (n_v - 1.0) / (n_total - 1.0))

    if level_of_measurement == "nominal":
        delta_sq = 1.0 - np.eye(v_count, dtype=np.float64)
    elif level_of_measurement == "interval":
        diff = values[:, None] - values[None, :]
        delta_sq = diff * diff
    else:
        raise ValueError(f"Unsupported level_of_measurement: {level_of_measurement}")

    d_o = float((o_matrix * delta_sq).sum())
    d_e = float((e_matrix * delta_sq).sum())
    return 1.0 - (d_o / d_e) if d_e > 0.0 else 1.0
