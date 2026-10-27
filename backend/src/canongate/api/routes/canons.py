"""Canon management, Pipeline A compilation, linting, friction, calibration & v1.1 PR routes."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from canongate.api.deps import SessionDep, get_canon, list_canon_ids, register_canon
from canongate.api.routes.submissions import _UPLOAD_DIR, _parse_submission_ast
from canongate.canon.compiler import compile_canon
from canongate.canon.impact import (
    _canon_to_yaml,
    calibrate_canon_rule,
    lint_canon,
    propose_canon_revision,
)
from canongate.domain.canon import (
    Canon,
    ColorToken,
    FactClaim,
    TermRule,
    TriggerObligation,
    VoiceProfile,
)
from canongate.engine.runner import run_checks_collect
from canongate.ledger.friction import compute_rule_friction, krippendorff_alpha
from canongate.parsers.bundle import BundleInput
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


class RecurringCategoryBreakdownDto(BaseModel):
    category: str
    total_flags: int
    open_count: int
    resolved_count: int
    overridden_count: int
    top_rule_id: str
    insight: str


class CanonFrictionResponse(BaseModel):
    canon_id: str
    canon_version: str
    krippendorff_alpha: float
    total_findings: int
    rules: list[RuleFrictionDto]
    revision_recommendations: list[str]
    category_breakdown: list[RecurringCategoryBreakdownDto] = []


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


class CustomTermInputDto(BaseModel):
    pattern_text: str
    preferred: str
    severity: int = 60


class CustomFactInputDto(BaseModel):
    text: str
    conditions: list[str] = []
    valid_until: str | None = None


class CustomColorInputDto(BaseModel):
    name: str
    hex: str
    max_delta_e: float = 3.0


class CustomTriggerInputDto(BaseModel):
    trigger_pattern: str
    required_disclaimer_text: str
    severity: int = 70


class CompileCanonRequest(BaseModel):
    canon_id: str
    version: str = "1.0"
    raw_text: str = ""
    attachments: list[CompileCanonAttachmentDto] = []
    custom_terms: list[CustomTermInputDto] = []
    custom_facts: list[CustomFactInputDto] = []
    custom_colors: list[CustomColorInputDto] = []
    custom_triggers: list[CustomTriggerInputDto] = []
    voice_max_words: int | None = None
    voice_passive_pct: float | None = None
    voice_fk_grade: float | None = None
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
    trigger_count: int = 0
    logo_count: int = 0
    has_voice_profile: bool = False
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
                source_text=getattr(t, "source_text", "") or t.note,
            )
        )
    for c in canon.palette:
        items.append(
            CanonRuleItemDto(
                id=c.id,
                rule_type="palette",
                label=f"[Palette] {c.id} — {c.name or c.hex} ({c.hex}, ΔE00 ≤ {c.max_delta_e})",
                max_delta_e=c.max_delta_e,
                source_text=getattr(c, "source_text", "") or f"{c.name}: {c.hex}",
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
                source_text=getattr(lg, "source_text", "") or lg.reference_path,
            )
        )
    for f in canon.facts:
        cond_str = f" [{'; '.join(f.conditions)}]" if f.conditions else ""
        short_t = f.text[:56] + ("…" if len(f.text) > 56 else "")
        items.append(
            CanonRuleItemDto(
                id=f.id,
                rule_type="fact",
                label=f"[Fact Claim] {f.id} — {short_t}{cond_str}",
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
    """Pipeline A: compile brand text/documents/assets into a grounded Canon behind Guards 1-3."""
    inputs: list[BundleInput] = []

    # Synthesize any structured custom rules into canonical lines so they pass Guards 1-3
    synthesized_lines: list[str] = []
    if req.raw_text.strip():
        synthesized_lines.append(req.raw_text.strip())
    for ct in req.custom_terms:
        if ct.pattern_text.strip() and ct.preferred.strip():
            synthesized_lines.append(
                f"Never use '{ct.pattern_text.strip()}', prefer '{ct.preferred.strip()}'."
            )
    for cc in req.custom_colors:
        hex_v = cc.hex.strip()
        if hex_v:
            if not hex_v.startswith("#"):
                hex_v = f"#{hex_v}"
            synthesized_lines.append(f"{cc.name.strip() or 'Brand Color'}: {hex_v.upper()}")
    for cf in req.custom_facts:
        if cf.text.strip():
            c_part = (
                f" ({'; '.join(c.strip() for c in cf.conditions if c.strip())})"
                if cf.conditions
                else ""
            )
            v_part = (
                f" valid until {cf.valid_until.strip()}"
                if cf.valid_until and cf.valid_until.strip()
                else ""
            )
            synthesized_lines.append(f"Approved Fact: {cf.text.strip()}{c_part}{v_part}")
    for ctr in req.custom_triggers:
        pat = ctr.trigger_pattern.strip()
        disc = ctr.required_disclaimer_text.strip()
        if pat and disc:
            synthesized_lines.append(f"Trigger: '{pat}' -> Disclaimer: '{disc}'")

    if synthesized_lines:
        inputs.append("\n\n".join(synthesized_lines))

    for att in req.attachments:
        try:
            raw_bytes = base64.b64decode(att.content_base64)
            ext = Path(att.filename).suffix.lower()
            if ext in (".png", ".jpg", ".jpeg", ".webp"):
                _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256(raw_bytes).hexdigest()[:12]
                safe_stem = "".join(
                    c if c.isalnum() or c in "-_" else "_" for c in Path(att.filename).stem
                )[:36]
                saved_path = _UPLOAD_DIR / f"logo_{safe_stem}_{digest}{ext}"
                saved_path.write_bytes(raw_bytes)
                inputs.append(saved_path)
            else:
                inputs.append((att.filename, raw_bytes))
        except Exception:
            continue

    from canongate.parsers.llm_table import MultiProviderJsonLLM

    llm_client = MultiProviderJsonLLM()
    canon, provenance = compile_canon(
        *inputs,
        canon_id=req.canon_id.strip() or "compiled-canon",
        version=req.version.strip() or "1.0",
        llm_client=llm_client if llm_client.is_enabled else None,
    )

    # Apply explicit custom overrides/additions if specified
    extra_terms = list(canon.terminology)
    existing_term_pats = {t.pattern_text.lower() for t in extra_terms}
    for idx, ct in enumerate(req.custom_terms):
        pat = ct.pattern_text.strip()
        pref = ct.preferred.strip()
        if pat and pref and pat.lower() not in existing_term_pats:
            existing_term_pats.add(pat.lower())
            extra_terms.append(
                TermRule(
                    id=f"term-custom-{idx + 1}",
                    pattern_text=pat,
                    preferred=pref,
                    severity=ct.severity,
                    note=f"Never use '{pat}', prefer '{pref}'.",
                )
            )

    extra_colors = list(canon.palette)
    existing_hex = {c.hex.upper() for c in extra_colors}
    for idx, cc in enumerate(req.custom_colors):
        hv = cc.hex.strip().upper()
        if hv and not hv.startswith("#"):
            hv = f"#{hv}"
        if len(hv) == 7 and hv not in existing_hex:
            existing_hex.add(hv)
            extra_colors.append(
                ColorToken(
                    id=f"color-custom-{idx + 1}",
                    hex=hv,
                    name=cc.name.strip() or f"Brand Color {idx + 1}",
                    max_delta_e=cc.max_delta_e,
                )
            )

    extra_facts = list(canon.facts)
    existing_fact_texts = {f.text.lower() for f in extra_facts}
    for idx, cf in enumerate(req.custom_facts):
        ft = cf.text.strip()
        if ft and ft.lower() not in existing_fact_texts:
            existing_fact_texts.add(ft.lower())
            extra_facts.append(
                FactClaim(
                    id=f"fact-custom-{idx + 1}",
                    text=ft,
                    conditions=tuple(c.strip() for c in cf.conditions if c.strip()),
                    valid_until=cf.valid_until.strip() if cf.valid_until else None,
                )
            )

    extra_triggers = list(canon.trigger_obligations)
    existing_trig_pats = {t.trigger_pattern.lower() for t in extra_triggers}
    for idx, ctr in enumerate(req.custom_triggers):
        tp = ctr.trigger_pattern.strip()
        dt = ctr.required_disclaimer_text.strip()
        if tp and dt and tp.lower() not in existing_trig_pats:
            existing_trig_pats.add(tp.lower())
            extra_triggers.append(
                TriggerObligation(
                    id=f"trigger-custom-{idx + 1}",
                    trigger_pattern=tp,
                    required_disclaimer_id=f"disc-custom-{idx + 1}",
                    required_disclaimer_text=dt,
                    severity=ctr.severity,
                )
            )

    vp = canon.voice_profile
    if (
        req.voice_max_words is not None
        or req.voice_passive_pct is not None
        or req.voice_fk_grade is not None
    ):
        vp = VoiceProfile(
            id="voice-custom",
            min_sentence_words=3,
            max_sentence_words=req.voice_max_words or (vp.max_sentence_words if vp else 28),
            max_passive_voice_pct=(
                req.voice_passive_pct
                if req.voice_passive_pct is not None
                else (vp.max_passive_voice_pct if vp else 20.0)
            ),
            max_flesch_kincaid_grade=(
                req.voice_fk_grade
                if req.voice_fk_grade is not None
                else (vp.max_flesch_kincaid_grade if vp else 11.0)
            ),
            severity=40,
        )

    canon = Canon(
        id=canon.id,
        version=canon.version,
        terminology=tuple(extra_terms),
        palette=tuple(extra_colors),
        facts=tuple(extra_facts),
        trigger_obligations=tuple(extra_triggers),
        voice_profile=vp,
        logos=canon.logos,
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
        trigger_count=len(canon.trigger_obligations),
        logo_count=len(canon.logos),
        has_voice_profile=canon.voice_profile is not None,
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


def _classify_finding_category(check_id: str) -> tuple[str, str]:
    if check_id.startswith("claim."):
        return (
            "Facts & Promotional Claims",
            (
                "Repeated qualifier drops or expired offers — ensure creators "
                "reference the approved KFS/product fact sheet."
            ),
        )
    if check_id.startswith("terminology."):
        return (
            "Terminology & Brand Language",
            (
                "Frequent banned-term usage — share preferred replacement glossary "
                "with agency and content writers."
            ),
        )
    if check_id.startswith("voice."):
        return (
            "Tone & Readability",
            (
                "Long sentences or high passive-voice ratio — consider calibrating "
                "sentence-length threshold if copy is technical."
            ),
        )
    if check_id.startswith("visual."):
        return (
            "Visual & Logo Consistency",
            "Off-palette hex drift or logo clear-space intrusion in promotional banners.",
        )
    if check_id.startswith("accessibility."):
        return (
            "Accessibility (WCAG 2.1 AA)",
            "Low text-on-background contrast (< 4.5:1) or missing image alt text.",
        )
    if check_id.startswith("trigger.") or check_id.startswith("legibility."):
        return (
            "Statutory Disclaimers & Prominence",
            (
                "Missing trigger disclaimers or visually subordinated fine print "
                "under CCPA 2022 rules."
            ),
        )
    return (
        "Security & Content Provenance",
        "Hidden low-contrast text, Unicode confusables, or missing C2PA asset provenance.",
    )


_RULE_ID_EXTRACT_RE = re.compile(r'"rule_id"\s*:\s*"([^"]+)"')


def _aggregate_canon_friction(
    findings: list,
) -> tuple[
    dict[str, dict[str, int]],
    dict[int, dict[int, int]],
    list[RecurringCategoryBreakdownDto],
]:
    rule_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "disputed": 0})
    reviewer_ratings: dict[int, dict[int, int]] = defaultdict(dict)
    cat_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "open": 0,
            "resolved": 0,
            "overridden": 0,
            "rules": defaultdict(int),
            "insight": "",
        }
    )

    for f in findings:
        rule_key = f.check_id
        p_json = f.payload_json
        if p_json and '"rule_id"' in p_json:
            m_rule = _RULE_ID_EXTRACT_RE.search(p_json)
            if m_rule and m_rule.group(1):
                rule_key = m_rule.group(1)
            else:
                try:
                    payload = json.loads(p_json)
                    if isinstance(payload.get("rule_ref"), dict) and payload["rule_ref"].get(
                        "rule_id"
                    ):
                        rule_key = payload["rule_ref"]["rule_id"]
                except Exception:
                    pass

        rule_stats[rule_key]["total"] += 1
        if f.resolution in ("overridden", "dismissed"):
            rule_stats[rule_key]["disputed"] += 1

        if f.resolved_by is not None:
            is_disputed = f.resolution in ("overridden", "dismissed")
            reviewer_ratings[f.resolved_by][f.id] = 1 if is_disputed else 0

        cat_name, cat_insight = _classify_finding_category(f.check_id)
        entry = cat_stats[cat_name]
        entry["total"] += 1
        entry["insight"] = cat_insight
        entry["rules"][rule_key] += 1
        if f.resolution == "open":
            entry["open"] += 1
        elif f.resolution in ("overridden", "dismissed"):
            entry["overridden"] += 1
        else:
            entry["resolved"] += 1

    category_dtos: list[RecurringCategoryBreakdownDto] = []
    for cat_name, st in sorted(cat_stats.items(), key=lambda x: x[1]["total"], reverse=True):
        top_rule = max(st["rules"].items(), key=lambda x: x[1])[0] if st["rules"] else "—"
        category_dtos.append(
            RecurringCategoryBreakdownDto(
                category=cat_name,
                total_flags=st["total"],
                open_count=st["open"],
                resolved_count=st["resolved"],
                overridden_count=st["overridden"],
                top_rule_id=top_rule,
                insight=st["insight"],
            )
        )

    return rule_stats, reviewer_ratings, category_dtos


@router.get("/{canon_id}/friction", response_model=CanonFrictionResponse)
async def get_canon_friction(
    canon_id: str,
    session: SessionDep,
) -> CanonFrictionResponse:
    """Calculate Beta-Binomial friction, recurring categories, and Krippendorff's alpha."""
    canon = get_canon(canon_id)
    findings = await repos.get_findings_for_canon(session, canon_id)
    rule_stats, reviewer_ratings, category_breakdown = _aggregate_canon_friction(findings)

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
        category_breakdown=category_breakdown,
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
    rule_stats, _, _ = _aggregate_canon_friction(findings)

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
    rule_stats, _, _ = _aggregate_canon_friction(findings)
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
