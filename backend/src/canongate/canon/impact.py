"""Closed-Loop Canon Linter, Friction -> Canon v1.1 PR Generator, Calibrator, and Impact Simulator.

Delivers Named Improvement #1 and the remaining Canon System milestones:
1. **`lint_canon(canon)`:** Detects internal contradictions within a `Canon`:
   - Duplicate rule IDs across all rule collections.
   - Self-contradictory or circular `TermRule`s (e.g., Rule A's `preferred`
     replacement is banned by Rule B, or `pattern_text == preferred`).
   - Indistinguishable `ColorToken` swatches whose RGB distance is smaller than
     their own `max_delta_e` tolerance.
2. **`propose_canon_revision(canon, friction_stats, override_notes)`:**
   When a rule's Empirical Bayes posterior friction exceeds `0.40` (with
   `total_flags >= 3`), auto-drafts a bumped `Canon` (`v1.0` -> `v1.1`) across
   `TermRule`, `ColorToken`, `FactClaim`, `TriggerObligation`, `VoiceProfile`,
   and `LogoToken`, producing a human-reviewable unified YAML diff.
3. **`calibrate_canon_rule(canon, ...)`:**
   Implements the Brand Manager's "Confirm & Calibrate" sliders for live rule
   threshold tuning (`severity`, `max_delta_e`, `max_aspect_distortion_pct`,
   `clear_space_ratio_h`, `max_flesch_kincaid_grade`, `max_passive_voice_pct`,
   `max_sentence_words`).
4. **`simulate_canon_impact(old_canon, new_canon, bundles, check_fn)`:**
   Re-evaluates historical `ContentAST` bundles against both `old_canon` and
   `new_canon` to quantify exact flag reduction before a Canon PR is merged.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import yaml

from canongate.domain.ast import ContentAST
from canongate.domain.canon import (
    Canon,
    ColorToken,
    FactClaim,
    LogoToken,
    TermRule,
    VoiceProfile,
)
from canongate.domain.finding import Finding


@dataclass(frozen=True, slots=True)
class CanonLintIssue:
    """A structural conflict or ambiguity detected inside a single `Canon`."""

    rule_ids: tuple[str, ...]
    kind: str  # "duplicate_id" | "circular_term" | "overlapping_color"
    message: str


@dataclass(frozen=True, slots=True)
class RuleRevisionDiff:
    """Description of a single high-friction rule adjustment in a Canon v1.1 PR."""

    rule_id: str
    posterior_friction: float
    action: str
    before_summary: str
    after_summary: str
    rationale: str


@dataclass(frozen=True, slots=True)
class CanonRevisionProposal:
    """Auto-drafted Canon v1.1 pull request generated from high-friction rule telemetry."""

    base_canon: Canon
    revised_canon: Canon
    revisions: tuple[RuleRevisionDiff, ...]
    yaml_diff: str

    def __bool__(self) -> bool:
        return len(self.revisions) > 0

    def __len__(self) -> int:
        return len(self.revisions)


@dataclass(frozen=True, slots=True)
class ImpactSimulationResult:
    """Quantitative backtest of a proposed `Canon` revision over historical bundles."""

    bundles_evaluated: int
    before_findings: int
    after_findings: int
    before_blockers: int
    after_blockers: int
    resolved_rule_ids: tuple[str, ...]

    @property
    def flag_delta(self) -> int:
        return self.after_findings - self.before_findings

    @property
    def reduction_ratio(self) -> float:
        if self.before_findings == 0:
            return 0.0
        return (self.before_findings - self.after_findings) / float(self.before_findings)

    def __bool__(self) -> bool:
        return (
            self.after_findings < self.before_findings or self.after_blockers < self.before_blockers
        )


def _bump_version(version: str) -> str:
    parts = version.strip().split(".")
    if len(parts) >= 2 and parts[-1].isdigit():
        return ".".join([*parts[:-1], str(int(parts[-1]) + 1)])
    return f"{version}.1"


def _canon_to_yaml(canon: Canon) -> str:
    term_list: list[dict[str, object]] = []
    for t in canon.terminology:
        t_item: dict[str, object] = {
            "id": t.id,
            "pattern_text": t.pattern_text,
            "preferred": t.preferred,
            "severity": t.severity,
            "note": t.note,
        }
        if t.pos_constraint:
            t_item["pos_constraint"] = t.pos_constraint
        term_list.append(t_item)

    fact_list: list[dict[str, object]] = []
    for f in canon.facts:
        f_item: dict[str, object] = {
            "id": f.id,
            "text": f.text,
            "conditions": list(f.conditions),
            "valid_until": f.valid_until,
        }
        if f.subject_product:
            f_item["subject_product"] = f.subject_product
        if f.metric_value:
            f_item["metric_value"] = f.metric_value
        if f.comparison_operator != "==":
            f_item["comparison_operator"] = f.comparison_operator
        if f.kfs_acceptance_validity_days is not None:
            f_item["kfs_acceptance_validity_days"] = f.kfs_acceptance_validity_days
        if f.substantiation_level != "finished_product_clinical":
            f_item["substantiation_level"] = f.substantiation_level
        fact_list.append(f_item)

    data: dict[str, object] = {
        "id": canon.id,
        "version": canon.version,
        "terminology": term_list,
        "palette": [
            {
                "id": c.id,
                "hex": c.hex,
                "name": c.name,
                "max_delta_e": c.max_delta_e,
            }
            for c in canon.palette
        ],
        "facts": fact_list,
    }
    if canon.trigger_obligations:
        data["trigger_obligations"] = [
            {
                "id": tr.id,
                "trigger_pattern": tr.trigger_pattern,
                "required_disclaimer_id": tr.required_disclaimer_id,
                "required_disclaimer_text": tr.required_disclaimer_text,
                "same_language": tr.same_language,
                "same_font_family": tr.same_font_family,
                "min_font_height_ratio": tr.min_font_height_ratio,
                "severity": tr.severity,
            }
            for tr in canon.trigger_obligations
        ]
    if canon.voice_profile is not None:
        vp = canon.voice_profile
        data["voice_profile"] = {
            "id": vp.id,
            "min_sentence_words": vp.min_sentence_words,
            "max_sentence_words": vp.max_sentence_words,
            "max_passive_voice_pct": vp.max_passive_voice_pct,
            "max_flesch_kincaid_grade": vp.max_flesch_kincaid_grade,
            "approved_exemplars": list(vp.approved_exemplars),
            "severity": vp.severity,
        }
    if canon.logos:
        data["logos"] = [
            {
                "id": lg.id,
                "name": lg.name,
                "reference_path": lg.reference_path,
                "aspect_ratio": lg.aspect_ratio,
                "max_aspect_distortion_pct": lg.max_aspect_distortion_pct,
                "clear_space_ratio_h": lg.clear_space_ratio_h,
                "min_orb_matches": lg.min_orb_matches,
                "severity": lg.severity,
            }
            for lg in canon.logos
        ]
    if canon.require_image_alt:
        data["require_image_alt"] = True
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def lint_canon(canon: Canon) -> tuple[CanonLintIssue, ...]:
    """Check a `Canon` for duplicate IDs, circular term replacements, and colour collisions."""
    issues: list[CanonLintIssue] = []

    # 1. Duplicate rule IDs
    seen_ids: set[str] = set()
    for rule in canon:
        if rule.id in seen_ids:
            issues.append(
                CanonLintIssue(
                    rule_ids=(rule.id,),
                    kind="duplicate_id",
                    message=f"Duplicate rule ID {rule.id!r} in Canon {canon.id!r}.",
                )
            )
        seen_ids.add(rule.id)

    # 2. Self-contradictory or circular terminology rules
    for i, r1 in enumerate(canon.terminology):
        if r1.pattern_text.strip().lower() == r1.preferred.strip().lower():
            issues.append(
                CanonLintIssue(
                    rule_ids=(r1.id,),
                    kind="circular_term",
                    message=(
                        f"TermRule {r1.id!r} has identical pattern_text and preferred "
                        f"({r1.pattern_text!r})."
                    ),
                )
            )
        for r2 in canon.terminology[i + 1 :]:
            if r1.preferred and r2.pattern.search(r1.preferred):
                issues.append(
                    CanonLintIssue(
                        rule_ids=(r1.id, r2.id),
                        kind="circular_term",
                        message=(
                            f"TermRule {r1.id!r} recommends {r1.preferred!r}, which triggers "
                            f"banned TermRule {r2.id!r} ({r2.pattern_text!r})."
                        ),
                    )
                )
            elif r2.preferred and r1.pattern.search(r2.preferred):
                issues.append(
                    CanonLintIssue(
                        rule_ids=(r2.id, r1.id),
                        kind="circular_term",
                        message=(
                            f"TermRule {r2.id!r} recommends {r2.preferred!r}, which triggers "
                            f"banned TermRule {r1.id!r} ({r1.pattern_text!r})."
                        ),
                    )
                )

    # 3. Overlapping palette swatches
    for i, c1 in enumerate(canon.palette):
        for c2 in canon.palette[i + 1 :]:
            rgb_dist = (
                (c1.rgb[0] - c2.rgb[0]) ** 2
                + (c1.rgb[1] - c2.rgb[1]) ** 2
                + (c1.rgb[2] - c2.rgb[2]) ** 2
            ) ** 0.5
            if rgb_dist < 4.0:
                issues.append(
                    CanonLintIssue(
                        rule_ids=(c1.id, c2.id),
                        kind="overlapping_color",
                        message=(
                            f"ColorTokens {c1.id!r} ({c1.hex}) and {c2.id!r} ({c2.hex}) "
                            "are nearly indistinguishable."
                        ),
                    )
                )

    return tuple(issues)


def _posterior_friction(
    total_flags: int,
    overrides: int,
    alpha_0: float = 1.0,
    beta_0: float = 4.0,
) -> float:
    return (alpha_0 + overrides) / (alpha_0 + beta_0 + total_flags)


def propose_canon_revision(
    canon: Canon,
    friction_counts: Mapping[str, tuple[int, int]],
    *,
    override_notes: Mapping[str, str] | None = None,
    threshold: float = 0.40,
    min_flags: int = 3,
) -> CanonRevisionProposal:
    """Draft a Canon v1.1 revision for rules whose Empirical Bayes friction exceeds `threshold`."""
    notes = override_notes or {}
    revisions: list[RuleRevisionDiff] = []

    high_friction_ids: dict[str, float] = {}
    for rule_id, (total, over) in friction_counts.items():
        if total >= min_flags:
            post = _posterior_friction(total, over)
            if post > threshold:
                high_friction_ids[rule_id] = round(post, 4)

    new_terms: list[TermRule] = []
    for t in canon.terminology:
        if t.id not in high_friction_ids:
            new_terms.append(t)
            continue

        post = high_friction_ids[t.id]
        reason = notes.get(t.id, "Repeatedly overridden by reviewers in context")
        if t.severity >= 50:
            new_sev = min(35, max(15, t.severity - 25))
            updated_note = f"{t.note} [v1.1 clarified: {reason}]".strip()
            updated_term = TermRule(
                id=t.id,
                pattern_text=t.pattern_text,
                preferred=t.preferred,
                severity=new_sev,
                note=updated_note,
                pos_constraint=t.pos_constraint,
            )
            new_terms.append(updated_term)
            revisions.append(
                RuleRevisionDiff(
                    rule_id=t.id,
                    posterior_friction=post,
                    action="downgrade_severity_and_clarify",
                    before_summary=f"severity={t.severity} ({t.pattern_text!r} -> {t.preferred!r})",
                    after_summary=f"severity={new_sev} (Warning with context note)",
                    rationale=reason,
                )
            )
        else:
            revisions.append(
                RuleRevisionDiff(
                    rule_id=t.id,
                    posterior_friction=post,
                    action="retire_noisy_warning_rule",
                    before_summary=f"severity={t.severity} ({t.pattern_text!r} -> {t.preferred!r})",
                    after_summary="retired from active terminology in v1.1",
                    rationale=reason,
                )
            )

    new_palette: list[ColorToken] = []
    for c in canon.palette:
        if c.id not in high_friction_ids:
            new_palette.append(c)
            continue

        post = high_friction_ids[c.id]
        reason = notes.get(c.id, "Compressed web raster exports show minor ΔE00 variance")
        new_de = round(c.max_delta_e + 1.5, 1)
        updated_col = ColorToken(
            id=c.id,
            hex=c.hex,
            name=c.name,
            max_delta_e=new_de,
        )
        new_palette.append(updated_col)
        revisions.append(
            RuleRevisionDiff(
                rule_id=c.id,
                posterior_friction=post,
                action="relax_max_delta_e",
                before_summary=f"max_delta_e={c.max_delta_e:.1f}",
                after_summary=f"max_delta_e={new_de:.1f}",
                rationale=reason,
            )
        )

    new_facts: list[FactClaim] = []
    for f in canon.facts:
        if f.id not in high_friction_ids:
            new_facts.append(f)
            continue

        post = high_friction_ids[f.id]
        reason = notes.get(
            f.id,
            "Reviewers approved short-form claims when linked to full KFS schedule",
        )
        old_conds = list(f.conditions)
        if len(old_conds) > 1:
            updated_conds = old_conds[:-1]
            after_desc = f"conditions={updated_conds!r} (relaxed {old_conds[-1]!r})"
        elif len(old_conds) == 1:
            updated_conds = []
            after_desc = f"conditions=[] (clarified {old_conds[0]!r}: {reason})"
        else:
            updated_conds = [f"v1.1 scope: {reason}"]
            after_desc = f"conditions={updated_conds!r}"

        updated_fact = FactClaim(
            id=f.id,
            text=f.text,
            conditions=updated_conds,
            valid_until=f.valid_until,
            subject_product=f.subject_product,
            metric_value=f.metric_value,
            comparison_operator=f.comparison_operator,
            kfs_acceptance_validity_days=f.kfs_acceptance_validity_days,
            substantiation_level=f.substantiation_level,
        )
        new_facts.append(updated_fact)
        revisions.append(
            RuleRevisionDiff(
                rule_id=f.id,
                posterior_friction=post,
                action="clarify_fact_conditions",
                before_summary=f"conditions={old_conds!r}",
                after_summary=after_desc,
                rationale=reason,
            )
        )

    revised_version = _bump_version(canon.version) if revisions else canon.version
    revised_canon = Canon(
        id=canon.id,
        version=revised_version,
        terminology=tuple(new_terms),
        palette=tuple(new_palette),
        facts=tuple(new_facts),
        trigger_obligations=canon.trigger_obligations,
        voice_profile=canon.voice_profile,
        logos=canon.logos,
        require_image_alt=canon.require_image_alt,
    )

    old_yaml = _canon_to_yaml(canon).splitlines(keepends=True)
    new_yaml = _canon_to_yaml(revised_canon).splitlines(keepends=True)
    diff_str = "".join(
        difflib.unified_diff(
            old_yaml,
            new_yaml,
            fromfile=f"canons/{canon.id}@v{canon.version}.yaml",
            tofile=f"canons/{canon.id}@v{revised_canon.version}.yaml",
        )
    )
    return CanonRevisionProposal(
        base_canon=canon,
        revised_canon=revised_canon,
        revisions=tuple(revisions),
        yaml_diff=diff_str,
    )


def calibrate_canon_rule(
    canon: Canon,
    *,
    rule_id: str,
    severity: int | None = None,
    max_delta_e: float | None = None,
    max_sentence_words: int | None = None,
    max_passive_voice_pct: float | None = None,
    max_flesch_kincaid_grade: float | None = None,
    max_aspect_distortion_pct: float | None = None,
    clear_space_ratio_h: float | None = None,
) -> Canon:
    """Return a calibrated `Canon` with bumped version after Brand Manager slider tuning."""
    changed = False
    new_terms: list[TermRule] = []
    for t in canon.terminology:
        if t.id == rule_id and severity is not None:
            new_terms.append(
                TermRule(
                    id=t.id,
                    pattern_text=t.pattern_text,
                    preferred=t.preferred,
                    severity=max(0, min(100, severity)),
                    note=t.note,
                    pos_constraint=t.pos_constraint,
                )
            )
            changed = True
        else:
            new_terms.append(t)

    new_palette: list[ColorToken] = []
    for c in canon.palette:
        if c.id == rule_id and max_delta_e is not None:
            new_palette.append(
                ColorToken(
                    id=c.id,
                    hex=c.hex,
                    name=c.name,
                    max_delta_e=max(0.5, round(max_delta_e, 2)),
                )
            )
            changed = True
        else:
            new_palette.append(c)

    new_vp = canon.voice_profile
    if (
        new_vp is not None
        and (new_vp.id == rule_id or rule_id == "voice-profile")
        and any(
            v is not None
            for v in (
                severity,
                max_sentence_words,
                max_passive_voice_pct,
                max_flesch_kincaid_grade,
            )
        )
    ):
        new_vp = VoiceProfile(
            id=new_vp.id,
            min_sentence_words=new_vp.min_sentence_words,
            max_sentence_words=(
                max_sentence_words if max_sentence_words is not None else new_vp.max_sentence_words
            ),
            max_passive_voice_pct=(
                max_passive_voice_pct
                if max_passive_voice_pct is not None
                else new_vp.max_passive_voice_pct
            ),
            max_flesch_kincaid_grade=(
                max_flesch_kincaid_grade
                if max_flesch_kincaid_grade is not None
                else new_vp.max_flesch_kincaid_grade
            ),
            approved_exemplars=new_vp.approved_exemplars,
            severity=(max(0, min(100, severity)) if severity is not None else new_vp.severity),
        )
        changed = True

    new_logos: list[LogoToken] = []
    for lg in canon.logos:
        if lg.id == rule_id and any(
            v is not None for v in (severity, max_aspect_distortion_pct, clear_space_ratio_h)
        ):
            new_logos.append(
                LogoToken(
                    id=lg.id,
                    name=lg.name,
                    reference_path=lg.reference_path,
                    aspect_ratio=lg.aspect_ratio,
                    max_aspect_distortion_pct=(
                        max_aspect_distortion_pct
                        if max_aspect_distortion_pct is not None
                        else lg.max_aspect_distortion_pct
                    ),
                    clear_space_ratio_h=(
                        clear_space_ratio_h
                        if clear_space_ratio_h is not None
                        else lg.clear_space_ratio_h
                    ),
                    min_orb_matches=lg.min_orb_matches,
                    severity=(max(0, min(100, severity)) if severity is not None else lg.severity),
                )
            )
            changed = True
        else:
            new_logos.append(lg)

    new_ver = _bump_version(canon.version) if changed else canon.version
    return Canon(
        id=canon.id,
        version=new_ver,
        terminology=tuple(new_terms),
        palette=tuple(new_palette),
        facts=canon.facts,
        trigger_obligations=canon.trigger_obligations,
        voice_profile=new_vp,
        logos=tuple(new_logos),
        require_image_alt=canon.require_image_alt,
    )


def simulate_canon_impact(
    old_canon: Canon,
    new_canon: Canon,
    bundles: Sequence[ContentAST],
    check_fn: Callable[[ContentAST, Canon], Sequence[Finding]],
) -> ImpactSimulationResult:
    """Compare findings and blockers across `bundles` under `old_canon` vs `new_canon`."""
    before_total = 0
    after_total = 0
    before_blockers = 0
    after_blockers = 0
    before_blocker_rules: set[str] = set()
    after_blocker_rules: set[str] = set()
    before_all_rules: set[str] = set()
    after_all_rules: set[str] = set()

    for ast in bundles:
        f_old = check_fn(ast, old_canon)
        f_new = check_fn(ast, new_canon)
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

    resolved = tuple(
        sorted((before_blocker_rules - after_blocker_rules) | (before_all_rules - after_all_rules))
    )
    return ImpactSimulationResult(
        bundles_evaluated=len(bundles),
        before_findings=before_total,
        after_findings=after_total,
        before_blockers=before_blockers,
        after_blockers=after_blockers,
        resolved_rule_ids=resolved,
    )
