"""Canon management routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from canongate.api.deps import CurrentUser, SessionDep, get_canon, list_canon_ids

router = APIRouter(prefix="/canons", tags=["canons"])


class CanonSummary(BaseModel):
    id: str
    version: str
    hash: str
    term_count: int
    color_count: int
    fact_count: int


@router.get("", response_model=list[CanonSummary])
async def list_canons() -> list[CanonSummary]:
    summaries = []
    for cid in list_canon_ids():
        canon = get_canon(cid)
        summaries.append(
            CanonSummary(
                id=canon.id,
                version=canon.version,
                hash=canon.hash,
                term_count=len(canon.terminology),
                color_count=len(canon.palette),
                fact_count=len(canon.facts),
            )
        )
    return summaries


@router.get("/{canon_id}", response_model=CanonSummary)
async def get_canon_detail(canon_id: str) -> CanonSummary:
    canon = get_canon(canon_id)
    return CanonSummary(
        id=canon.id,
        version=canon.version,
        hash=canon.hash,
        term_count=len(canon.terminology),
        color_count=len(canon.palette),
        fact_count=len(canon.facts),
    )


class RuleFrictionDto(BaseModel):
    rule_id: str
    total_flags: int
    overrides_and_disputes: int
    raw_friction: float
    posterior_friction: float
    needs_canon_revision: bool
    proposed_action: str | None = None


class CanonFrictionResponse(BaseModel):
    canon_id: str
    canon_version: str
    krippendorff_alpha: float
    total_findings: int
    rules: list[RuleFrictionDto]
    revision_recommendations: list[str]


@router.get("/{canon_id}/friction", response_model=CanonFrictionResponse)
async def get_canon_friction(
    canon_id: str,
    session: SessionDep,
) -> CanonFrictionResponse:
    """Calculate Empirical Bayes Beta-Binomial guideline friction and Krippendorff's alpha."""
    import json
    from collections import defaultdict
    from canongate.ledger.friction import compute_rule_friction, krippendorff_alpha
    from canongate.store import repos

    canon = get_canon(canon_id)
    findings = await repos.get_findings_for_canon(session, canon_id)

    # Group by rule_id (falling back to check_id)
    rule_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "disputed": 0})
    # Reviewer matrix by resolved_by for Krippendorff's alpha
    reviewer_ratings: dict[int, dict[int, int]] = defaultdict(dict)

    for f in findings:
        rule_key = f.check_id
        if f.payload_json:
            try:
                payload = json.loads(f.payload_json)
                if isinstance(payload.get("rule_ref"), dict) and payload["rule_ref"].get("rule_id"):
                    rule_key = payload["rule_ref"]["rule_id"]
            except Exception:
                pass

        rule_stats[rule_key]["total"] += 1
        if f.resolution in ("overridden", "dismissed"):
            rule_stats[rule_key]["disputed"] += 1

        if f.resolved_by is not None:
            # 0 for accepted, 1 for disputed/overridden
            reviewer_ratings[f.resolved_by][f.id] = 1 if f.resolution in ("overridden", "dismissed") else 0

    rule_dtos: list[RuleFrictionDto] = []
    recommendations: list[str] = []

    for rule_id, stats in rule_stats.items():
        report = compute_rule_friction(
            rule_id=rule_id,
            total_flags=stats["total"],
            overrides_and_disputes=stats["disputed"],
        )
        action = None
        if report.needs_canon_revision:
            action = f"Generate Canon v1.1 PR: relax rule '{rule_id}' due to {report.posterior_friction:.1%} friction"
            recommendations.append(action)

        rule_dtos.append(
            RuleFrictionDto(
                rule_id=report.rule_id,
                total_flags=report.total_flags,
                overrides_and_disputes=report.overrides_and_disputes,
                raw_friction=report.raw_friction,
                posterior_friction=report.posterior_friction,
                needs_canon_revision=report.needs_canon_revision,
                proposed_action=action,
            )
        )

    # Compute Krippendorff's alpha across all reviewers and finding units
    all_units = list({f.id for f in findings if f.resolved_by is not None})
    if len(reviewer_ratings) >= 2 and len(all_units) >= 1:
        import numpy as np
        matrix = []
        for r_id in reviewer_ratings:
            row = [reviewer_ratings[r_id].get(u, np.nan) for u in all_units]
            matrix.append(row)
        alpha = krippendorff_alpha(matrix, "nominal")
    else:
        alpha = 1.0

    return CanonFrictionResponse(
        canon_id=canon.id,
        canon_version=canon.version,
        krippendorff_alpha=round(float(alpha), 4),
        total_findings=len(findings),
        rules=rule_dtos,
        revision_recommendations=recommendations,
    )
