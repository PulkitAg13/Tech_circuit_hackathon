"""Canon management, linting, friction telemetry, and v1.1 PR simulation routes."""

from __future__ import annotations

import json
from collections import defaultdict

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from canongate.api.deps import SessionDep, get_canon, list_canon_ids
from canongate.api.routes.submissions import _parse_submission_ast
from canongate.canon.impact import lint_canon, propose_canon_revision
from canongate.domain.canon import Canon
from canongate.engine.runner import run_checks_collect
from canongate.ledger.friction import compute_rule_friction, krippendorff_alpha
from canongate.store import repos

router = APIRouter(prefix="/canons", tags=["canons"])


class CanonSummary(BaseModel):
    id: str
    version: str
    hash: str
    term_count: int
    color_count: int
    fact_count: int


class CanonLintIssueDto(BaseModel):
    rule_ids: list[str]
    kind: str
    message: str


class CanonLintResponse(BaseModel):
    canon_id: str
    canon_version: str
    is_valid: bool
    issues: list[CanonLintIssueDto]


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


class RuleRevisionDiffDto(BaseModel):
    rule_id: str
    posterior_friction: float
    action: str
    before_summary: str
    after_summary: str
    rationale: str


class CanonRevisionPrRequest(BaseModel):
    override_notes: dict[str, str] = {}
    threshold: float = 0.40
    min_flags: int = 3


class CanonRevisionPrResponse(BaseModel):
    canon_id: str
    base_version: str
    proposed_version: str
    has_changes: bool
    revisions: list[RuleRevisionDiffDto]
    yaml_diff: str
    bundles_evaluated: int
    before_findings: int
    after_findings: int
    before_blockers: int
    after_blockers: int
    reduction_ratio: float
    resolved_rule_ids: list[str]


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


@router.get("/{canon_id}/lint", response_model=CanonLintResponse)
async def get_canon_lint(canon_id: str) -> CanonLintResponse:
    """Check a Canon for duplicate IDs, circular terminology rules, and colour collisions."""
    canon = get_canon(canon_id)
    issues = lint_canon(canon)
    return CanonLintResponse(
        canon_id=canon.id,
        canon_version=canon.version,
        is_valid=len(issues) == 0,
        issues=[
            CanonLintIssueDto(
                rule_ids=list(iss.rule_ids),
                kind=iss.kind,
                message=iss.message,
            )
            for iss in issues
        ],
    )


def _aggregate_canon_friction(
    findings: list,
) -> tuple[dict[str, dict[str, int]], dict[int, dict[int, int]]]:
    rule_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "disputed": 0})
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
            is_disputed = f.resolution in ("overridden", "dismissed")
            reviewer_ratings[f.resolved_by][f.id] = 1 if is_disputed else 0

    return rule_stats, reviewer_ratings


@router.get("/{canon_id}/friction", response_model=CanonFrictionResponse)
async def get_canon_friction(
    canon_id: str,
    session: SessionDep,
) -> CanonFrictionResponse:
    """Calculate Empirical Bayes Beta-Binomial guideline friction and Krippendorff's alpha."""
    canon = get_canon(canon_id)
    findings = await repos.get_findings_for_canon(session, canon_id)
    rule_stats, reviewer_ratings = _aggregate_canon_friction(findings)

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
            action = (
                f"Generate Canon v1.1 PR: relax rule '{rule_id}' "
                f"due to {report.posterior_friction:.1%} friction"
            )
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

    all_units = list({f.id for f in findings if f.resolved_by is not None})
    if len(reviewer_ratings) >= 2 and len(all_units) >= 1:
        matrix = [
            [reviewer_ratings[r_id].get(u, np.nan) for u in all_units] for r_id in reviewer_ratings
        ]
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


async def _simulate_async_impact(
    old_canon: Canon,
    new_canon: Canon,
    raw_contents: list[str],
) -> tuple[int, int, int, int, list[str]]:
    before_total = 0
    after_total = 0
    before_blockers = 0
    after_blockers = 0
    before_blocker_rules: set[str] = set()
    after_blocker_rules: set[str] = set()
    before_all_rules: set[str] = set()
    after_all_rules: set[str] = set()

    for raw in raw_contents:
        ast = _parse_submission_ast(raw)
        f_old = await run_checks_collect(ast, old_canon)
        f_new = await run_checks_collect(ast, new_canon)
        before_total += len(f_old)
        after_total += len(f_new)
        before_blockers += sum(1 for f in f_old if f.is_blocker)
        after_blockers += sum(1 for f in f_new if f.is_blocker)
        for f in f_old:
            before_all_rules.add(f.rule_ref.rule_id)
            if f.is_blocker:
                before_blocker_rules.add(f.rule_ref.rule_id)
        for f in f_new:
            after_all_rules.add(f.rule_ref.rule_id)
            if f.is_blocker:
                after_blocker_rules.add(f.rule_ref.rule_id)

    resolved = sorted(
        (before_blocker_rules - after_blocker_rules) | (before_all_rules - after_all_rules)
    )
    return before_total, after_total, before_blockers, after_blockers, resolved


@router.post("/{canon_id}/propose-pr", response_model=CanonRevisionPrResponse)
async def propose_canon_pr(
    canon_id: str,
    session: SessionDep,
    req: CanonRevisionPrRequest | None = None,
) -> CanonRevisionPrResponse:
    """Auto-draft a Canon v1.1 revision from friction telemetry and backtest on historical runs."""
    params = req or CanonRevisionPrRequest()
    canon = get_canon(canon_id)
    findings = await repos.get_findings_for_canon(session, canon_id)
    rule_stats, _ = _aggregate_canon_friction(findings)

    friction_counts = {
        rule_id: (stats["total"], stats["disputed"]) for rule_id, stats in rule_stats.items()
    }
    proposal = propose_canon_revision(
        canon,
        friction_counts,
        override_notes=params.override_notes,
        threshold=params.threshold,
        min_flags=params.min_flags,
    )

    all_subs = await repos.list_submissions(session, limit=200)
    canon_raws = [s.raw_content for s in all_subs if s.canon_id == canon_id]
    (
        before_findings,
        after_findings,
        before_blockers,
        after_blockers,
        resolved_ids,
    ) = await _simulate_async_impact(canon, proposal.revised_canon, canon_raws)

    reduction_ratio = (
        round((before_findings - after_findings) / float(before_findings), 4)
        if before_findings > 0
        else 0.0
    )

    return CanonRevisionPrResponse(
        canon_id=canon.id,
        base_version=canon.version,
        proposed_version=proposal.revised_canon.version,
        has_changes=bool(proposal),
        revisions=[
            RuleRevisionDiffDto(
                rule_id=rev.rule_id,
                posterior_friction=rev.posterior_friction,
                action=rev.action,
                before_summary=rev.before_summary,
                after_summary=rev.after_summary,
                rationale=rev.rationale,
            )
            for rev in proposal.revisions
        ],
        yaml_diff=proposal.yaml_diff,
        bundles_evaluated=len(canon_raws),
        before_findings=before_findings,
        after_findings=after_findings,
        before_blockers=before_blockers,
        after_blockers=after_blockers,
        reduction_ratio=reduction_ratio,
        resolved_rule_ids=resolved_ids,
    )
