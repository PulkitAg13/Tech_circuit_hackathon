"""Canon management, Pipeline A compilation, linting, friction, calibration & v1.1 PR routes."""

from __future__ import annotations

import base64
import json
from collections import defaultdict

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from canongate.api.deps import SessionDep, get_canon, list_canon_ids, register_canon
from canongate.api.routes.submissions import _parse_submission_ast
from canongate.canon.compiler import compile_canon
from canongate.canon.impact import (
    _canon_to_yaml,
    calibrate_canon_rule,
    lint_canon,
    propose_canon_revision,
)
from canongate.domain.canon import Canon
from canongate.engine.runner import run_checks_collect
from canongate.ledger.friction import compute_rule_friction, krippendorff_alpha
from canongate.parsers.bundle import BundleInput
from canongate.parsers.llm_table import MultiProviderJsonLLM
from canongate.store import repos

router = APIRouter(prefix="/canons", tags=["canons"])


class CanonRuleItemDto(BaseModel):
    id: str
    rule_type: str  # terminology | palette | fact | trigger | voice | logo
    label: str
    severity: int | None = None
    max_delta_e: float | None = None
    max_sentence_words: int | None = None
    max_passive_voice_pct: float | None = None
    max_flesch_kincaid_grade: float | None = None
    max_aspect_distortion_pct: float | None = None
    clear_space_ratio_h: float | None = None
    source_text: str = ""


class CanonSummary(BaseModel):
    id: str
    version: str
    hash: str
    term_count: int
    color_count: int
    fact_count: int
    trigger_count: int = 0
    logo_count: int = 0
    has_voice_profile: bool = False
    rules: list[CanonRuleItemDto] = []


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
    persist: bool = False


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


class CalibrateCanonRuleRequest(BaseModel):
    rule_id: str
    severity: int | None = None
    max_delta_e: float | None = None
    max_sentence_words: int | None = None
    max_passive_voice_pct: float | None = None
    max_flesch_kincaid_grade: float | None = None
    max_aspect_distortion_pct: float | None = None
    clear_space_ratio_h: float | None = None
    persist: bool = False


class CalibrateCanonRuleResponse(BaseModel):
    canon_id: str
    previous_version: str
    new_version: str
    new_hash: str
    yaml_preview: str


class CompileCanonAttachmentDto(BaseModel):
    filename: str
    content_base64: str


class CompileCanonRequest(BaseModel):
    canon_id: str
    version: str = "1.0"
    raw_text: str = ""
    attachments: list[CompileCanonAttachmentDto] = []
    persist: bool = False


class GroundedRuleProvenanceDto(BaseModel):
    rule_id: str
    rule_kind: str
    start: int
    end: int
    source_text: str
    raw_anchor_recall: float
    effective_anchor_recall: float
    recovered_conditions: list[str]
    round_trip_nli_score: float
    alignment_status: str


class CompileCanonResponse(BaseModel):
    canon_id: str
    version: str
    hash: str
    term_count: int
    color_count: int
    fact_count: int
    yaml_preview: str
    provenance: list[GroundedRuleProvenanceDto]


def _extract_canon_rules(canon: Canon) -> list[CanonRuleItemDto]:
    items: list[CanonRuleItemDto] = []
    for t in canon.terminology:
        items.append(
            CanonRuleItemDto(
                id=t.id,
                rule_type="terminology",
                label=(
                    f"[Terminology] {t.id} — '{t.pattern_text}' → '{t.preferred}' (S={t.severity})"
                ),
                severity=t.severity,
                source_text=getattr(t, "source_text", ""),
            )
        )
    for c in canon.palette:
        items.append(
            CanonRuleItemDto(
                id=c.id,
                rule_type="palette",
                label=f"[Palette] {c.id} — {c.name or c.hex} ({c.hex}, ΔE00 ≤ {c.max_delta_e})",
                max_delta_e=c.max_delta_e,
                source_text=getattr(c, "source_text", ""),
            )
        )
    if canon.voice_profile is not None:
        vp = canon.voice_profile
        items.append(
            CanonRuleItemDto(
                id=vp.id,
                rule_type="voice",
                label=(
                    f"[Voice Profile] {vp.id} — ≤{vp.max_sentence_words}w, "
                    f"passive ≤{vp.max_passive_voice_pct}%, "
                    f"FK ≤{vp.max_flesch_kincaid_grade} (S={vp.severity})"
                ),
                severity=vp.severity,
                max_sentence_words=vp.max_sentence_words,
                max_passive_voice_pct=vp.max_passive_voice_pct,
                max_flesch_kincaid_grade=vp.max_flesch_kincaid_grade,
                source_text=getattr(vp, "source_text", ""),
            )
        )
    for lg in canon.logos:
        items.append(
            CanonRuleItemDto(
                id=lg.id,
                rule_type="logo",
                label=(
                    f"[Logo ORB] {lg.id} — {lg.name or lg.id} "
                    f"(distortion ≤{lg.max_aspect_distortion_pct}%, "
                    f"clear space {lg.clear_space_ratio_h}H, S={lg.severity})"
                ),
                severity=lg.severity,
                max_aspect_distortion_pct=lg.max_aspect_distortion_pct,
                clear_space_ratio_h=lg.clear_space_ratio_h,
                source_text=getattr(lg, "source_text", ""),
            )
        )
    for f in canon.facts:
        items.append(
            CanonRuleItemDto(
                id=f.id,
                rule_type="fact",
                label=f"[Fact Claim] {f.id} — {f.text[:56]}{'…' if len(f.text) > 56 else ''}",
                source_text=getattr(f, "source_text", "") or f.text,
            )
        )
    for tr in canon.trigger_obligations:
        items.append(
            CanonRuleItemDto(
                id=tr.id,
                rule_type="trigger",
                label=f"[Trigger Obligation] {tr.id} — IF '{tr.trigger_pattern}' (S={tr.severity})",
                severity=tr.severity,
                source_text=getattr(tr, "source_text", "") or tr.required_disclaimer_text,
            )
        )
    return items


def _to_summary(canon: Canon) -> CanonSummary:
    return CanonSummary(
        id=canon.id,
        version=canon.version,
        hash=canon.hash,
        term_count=len(canon.terminology),
        color_count=len(canon.palette),
        fact_count=len(canon.facts),
        trigger_count=len(canon.trigger_obligations),
        logo_count=len(canon.logos),
        has_voice_profile=canon.voice_profile is not None,
        rules=_extract_canon_rules(canon),
    )


@router.get("", response_model=list[CanonSummary])
async def list_canons() -> list[CanonSummary]:
    return [_to_summary(get_canon(cid)) for cid in list_canon_ids()]


@router.post("/compile", response_model=CompileCanonResponse, status_code=201)
async def compile_brand_canon(req: CompileCanonRequest) -> CompileCanonResponse:
    """Pipeline A endpoint: compile brand text/documents into a grounded Canon behind Guards 1-3."""
    inputs: list[BundleInput] = []
    if req.raw_text.strip():
        inputs.append(req.raw_text)
    for att in req.attachments:
        try:
            raw_bytes = base64.b64decode(att.content_base64)
            inputs.append((att.filename, raw_bytes))
        except Exception:
            continue

    llm_client = MultiProviderJsonLLM()
    canon, provenance = compile_canon(
        *inputs,
        canon_id=req.canon_id.strip() or "compiled-canon",
        version=req.version.strip() or "1.0",
        llm_client=llm_client if llm_client.is_enabled else None,
    )

    register_canon(canon, persist_yaml=req.persist)

    prov_dtos = [
        GroundedRuleProvenanceDto(
            rule_id=p.rule_id,
            rule_kind=p.rule_kind,
            start=p.char_interval.start,
            end=p.char_interval.end,
            source_text=p.source_text,
            raw_anchor_recall=p.anchor_audit.raw_recall if p.anchor_audit else 1.0,
            effective_anchor_recall=p.anchor_audit.effective_recall if p.anchor_audit else 1.0,
            recovered_conditions=list(p.anchor_audit.recovered_conditions)
            if p.anchor_audit
            else [],
            round_trip_nli_score=p.round_trip_nli_score,
            alignment_status=p.alignment_status,
        )
        for p in provenance
    ]

    return CompileCanonResponse(
        canon_id=canon.id,
        version=canon.version,
        hash=canon.hash,
        term_count=len(canon.terminology),
        color_count=len(canon.palette),
        fact_count=len(canon.facts),
        yaml_preview=_canon_to_yaml(canon),
        provenance=prov_dtos,
    )


@router.get("/{canon_id}", response_model=CanonSummary)
async def get_canon_detail(canon_id: str) -> CanonSummary:
    return _to_summary(get_canon(canon_id))


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


@router.post("/{canon_id}/apply-pr", response_model=CanonSummary)
async def apply_canon_pr(
    canon_id: str,
    session: SessionDep,
    req: CanonRevisionPrRequest | None = None,
) -> CanonSummary:
    """Merge and activate the proposed Canon v1.1 revision in the live Canon registry."""
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
    register_canon(proposal.revised_canon, persist_yaml=params.persist)
    return _to_summary(proposal.revised_canon)


@router.post("/{canon_id}/calibrate", response_model=CalibrateCanonRuleResponse)
async def calibrate_canon_endpoint(
    canon_id: str,
    req: CalibrateCanonRuleRequest,
) -> CalibrateCanonRuleResponse:
    """Brand Manager Confirm & Calibrate slider endpoint to tune rule thresholds live."""
    canon = get_canon(canon_id)
    updated = calibrate_canon_rule(
        canon,
        rule_id=req.rule_id,
        severity=req.severity,
        max_delta_e=req.max_delta_e,
        max_sentence_words=req.max_sentence_words,
        max_passive_voice_pct=req.max_passive_voice_pct,
        max_flesch_kincaid_grade=req.max_flesch_kincaid_grade,
        max_aspect_distortion_pct=req.max_aspect_distortion_pct,
        clear_space_ratio_h=req.clear_space_ratio_h,
    )
    register_canon(updated, persist_yaml=req.persist)
    return CalibrateCanonRuleResponse(
        canon_id=updated.id,
        previous_version=canon.version,
        new_version=updated.version,
        new_hash=updated.hash,
        yaml_preview=_canon_to_yaml(updated),
    )
