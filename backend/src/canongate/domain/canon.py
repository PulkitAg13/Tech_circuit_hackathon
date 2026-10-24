r"""Canon: the machine-readable representation of all five brand governance schemas.

Implements the complete five-schema specification from Round 1 Plan §3.3 (p. 5):
1. `FactClaim` (`FactClaimSchema`): `subject_product`, `metric_value`,
   `comparison_operator`, `valid_until`, `kfs_acceptance_validity_days`,
   `substantiation_level`, and `conditions`.
2. `TriggerObligation` (`TriggerObligationSchema`): `IF trigger_pattern THEN
   required_disclaimer_id`, with `same_language`, `same_font_family`, and
   `min_font_height_ratio` prominence bounds.
3. `TermRule` (`TerminologySchema`): banned terms, preferred replacements, and
   `pos_constraint` part-of-speech constraints.
4. `VoiceProfile` (`VoiceProfileSchema`): sentence-length bounds, maximum
   passive-voice %, Flesch-Kincaid grade ceiling, and approved brand-voice
   exemplars.
5. `ColorToken` & `LogoToken` (`VisualTokenSchema`): approved hex codes with
   CIE LAB $\Delta E_{00}$ tolerance, reference logo ORB aspect distortion
   ceiling ($\le 2\%$), and clear-space ratio ($0.5H$).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from pydantic import Field

from canongate.domain.types import CanonHash, FrozenModel, computed_field


@lru_cache(maxsize=512)
def _compile_term_pattern(pattern_text: str) -> re.Pattern[str]:
    r"""Compile a case-insensitive boundary regex for `pattern_text`.

    Uses standard `\b` word boundaries when the leading/trailing character is
    alphanumeric (`\w`), and lookaround boundaries `(?<!\w)` / `(?!\w)` when the
    leading/trailing character is a symbol (such as `%`, `₹`, `$`, `#`), avoiding
    the Python `re` trap where `\b100%\b` fails to match before whitespace.
    """
    if not pattern_text:
        return re.compile(r"(?!x)x")
    lead = r"\b" if (pattern_text[0].isalnum() or pattern_text[0] == "_") else r"(?<!\w)"
    tail = r"\b" if (pattern_text[-1].isalnum() or pattern_text[-1] == "_") else r"(?!\w)"
    return re.compile(f"{lead}{re.escape(pattern_text)}{tail}", re.IGNORECASE)


@lru_cache(maxsize=256)
def _compile_trigger_pattern(trigger_pattern: str) -> re.Pattern[str]:
    """Compile a trigger obligation pattern (supporting regex or literal phrase)."""
    if not trigger_pattern:
        return re.compile(r"(?!x)x")
    try:
        return re.compile(trigger_pattern, re.IGNORECASE)
    except re.error:
        return _compile_term_pattern(trigger_pattern)


@lru_cache(maxsize=256)
def _parse_hex_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        raise ValueError(f"Invalid hex colour: {hex_str!r}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ── Rule reference ───────────────────────────────────────────────────


class Rule(FrozenModel, frozen=True):
    """Generic rule reference used in findings to point back at the Canon source."""

    rule_id: str
    rule_type: str  # "term", "color", "fact", "trigger", "voice", "logo", etc.
    source_text: str = ""  # the raw text from the brand book, for explainability


# ── Rule models (5 Schemas from Round 1 Plan §3.3) ───────────────────


class TermRule(FrozenModel, frozen=True):
    """TerminologySchema: a banned term with preferred replacement and POS constraint."""

    id: str
    pattern_text: str  # raw string, compiled into a cached regex at runtime
    preferred: str
    severity: Annotated[int, Field(ge=1, le=100)] = 60
    note: str = ""
    pos_constraint: str | None = None  # e.g. "NOUN", "VERB", "ADJ", "ADV"

    @property
    def pattern(self) -> re.Pattern[str]:
        return _compile_term_pattern(self.pattern_text)

    def finditer(self, text: str) -> Iterator[re.Match[str]]:
        return self.pattern.finditer(text)

    def __contains__(self, text: str) -> bool:
        return bool(self.pattern.search(text))

    def to_rule_ref(self) -> Rule:
        return Rule(rule_id=self.id, rule_type="term", source_text=self.note or self.pattern_text)


class ColorToken(FrozenModel, frozen=True):
    """VisualTokenSchema (Palette): an approved brand colour with CIEDE2000 tolerance."""

    id: str
    hex: str  # e.g. "#1A2B3C"
    name: str = ""
    max_delta_e: float = 3.0  # maximum ΔE00 before a Warning

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rgb(self) -> tuple[int, int, int]:
        return _parse_hex_rgb(self.hex)

    def __str__(self) -> str:
        return f"{self.name} ({self.hex})" if self.name else self.hex

    def to_rule_ref(self) -> Rule:
        return Rule(rule_id=self.id, rule_type="color", source_text=str(self))


class LogoToken(FrozenModel, frozen=True):
    """VisualTokenSchema (Logo ORB): reference logo with aspect & clear-space bounds."""

    id: str
    name: str = "Brand Logo"
    reference_path: str = ""
    aspect_ratio: float = 1.0
    max_aspect_distortion_pct: float = 2.0  # <= 2% aspect ratio distortion
    clear_space_ratio_h: float = 0.50  # 0.5H clear space around logo
    min_orb_matches: int = 8
    severity: Annotated[int, Field(ge=1, le=100)] = 65

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"

    def to_rule_ref(self) -> Rule:
        return Rule(rule_id=self.id, rule_type="logo", source_text=str(self))


class FactClaim(FrozenModel, frozen=True):
    """FactClaimSchema: an approved factual claim with conditions and KFS metadata."""

    id: str
    text: str
    conditions: tuple[str, ...] = ()
    valid_until: str | None = None  # ISO date
    subject_product: str = ""
    metric_value: str = ""
    comparison_operator: str = "=="
    kfs_acceptance_validity_days: int | None = None
    substantiation_level: str = "finished_product_clinical"

    def __str__(self) -> str:
        return self.text

    def to_rule_ref(self) -> Rule:
        return Rule(rule_id=self.id, rule_type="fact", source_text=self.text)


class TriggerObligation(FrozenModel, frozen=True):
    """TriggerObligationSchema: IF trigger_pattern THEN required_disclaimer_id."""

    id: str
    trigger_pattern: str
    required_disclaimer_id: str
    required_disclaimer_text: str = ""
    same_language: bool = True
    same_font_family: bool = True
    min_font_height_ratio: float = 0.50
    severity: Annotated[int, Field(ge=1, le=100)] = 75

    @property
    def pattern(self) -> re.Pattern[str]:
        return _compile_trigger_pattern(self.trigger_pattern)

    def __str__(self) -> str:
        return f"IF {self.trigger_pattern!r} THEN {self.required_disclaimer_id!r}"

    def to_rule_ref(self) -> Rule:
        return Rule(
            rule_id=self.id,
            rule_type="trigger_obligation",
            source_text=self.required_disclaimer_text or str(self),
        )


class VoiceProfile(FrozenModel, frozen=True):
    """VoiceProfileSchema: sentence-length, passive-voice %, Flesch-Kincaid & exemplars."""

    id: str = "voice-default"
    max_sentence_words: int = 28
    min_sentence_words: int = 2
    max_passive_voice_pct: float = 20.0
    max_flesch_kincaid_grade: float = 12.0
    approved_exemplars: tuple[str, ...] = ()
    min_exemplar_similarity: float = 0.15
    severity: Annotated[int, Field(ge=1, le=100)] = 40

    def __str__(self) -> str:
        return (
            f"VoiceProfile(max_words={self.max_sentence_words}, "
            f"max_passive={self.max_passive_voice_pct}%, "
            f"max_fk_grade={self.max_flesch_kincaid_grade})"
        )

    def to_rule_ref(self) -> Rule:
        return Rule(rule_id=self.id, rule_type="voice", source_text=str(self))


CanonRule = TermRule | ColorToken | FactClaim | TriggerObligation | VoiceProfile | LogoToken

_TermHashKey = tuple[str, str, str, int, str, str | None]
_PaletteHashKey = tuple[str, str, str, float, tuple[int, int, int]]
_FactHashKey = tuple[
    str,
    str,
    tuple[str, ...],
    str | None,
    str,
    str,
    str,
    int | None,
    str,
]
_TriggerHashKey = tuple[str, str, str, str, bool, bool, float, int]
_VoiceHashKey = tuple[str, int, int, float, float, tuple[str, ...], float, int] | None
_LogoHashKey = tuple[str, str, str, float, float, float, int, int]


@lru_cache(maxsize=128)
def _compute_canon_hash_cached(
    canon_id: str,
    version: str,
    terms_key: tuple[_TermHashKey, ...],
    palette_key: tuple[_PaletteHashKey, ...],
    facts_key: tuple[_FactHashKey, ...],
    triggers_key: tuple[_TriggerHashKey, ...] = (),
    voice_key: _VoiceHashKey = None,
    logos_key: tuple[_LogoHashKey, ...] = (),
    require_image_alt: bool = False,
) -> CanonHash:
    facts_payload = []
    for (
        fid,
        text,
        conds,
        valid_until,
        subj,
        metric,
        comp_op,
        kfs_days,
        sub_level,
    ) in facts_key:
        f_dict: dict[str, object] = {
            "conditions": list(conds),
            "id": fid,
            "text": text,
            "valid_until": valid_until,
        }
        if subj:
            f_dict["subject_product"] = subj
        if metric:
            f_dict["metric_value"] = metric
        if comp_op != "==":
            f_dict["comparison_operator"] = comp_op
        if kfs_days is not None:
            f_dict["kfs_acceptance_validity_days"] = kfs_days
        if sub_level != "finished_product_clinical":
            f_dict["substantiation_level"] = sub_level
        facts_payload.append(f_dict)

    terms_payload = []
    for tid, pat, pref, sev, note, pos_c in terms_key:
        t_dict: dict[str, object] = {
            "id": tid,
            "note": note,
            "pattern_text": pat,
            "preferred": pref,
            "severity": sev,
        }
        if pos_c:
            t_dict["pos_constraint"] = pos_c
        terms_payload.append(t_dict)

    payload: dict[str, object] = {
        "facts": facts_payload,
        "id": canon_id,
        "palette": [
            {
                "hex": hex_val,
                "id": cid,
                "max_delta_e": max_de,
                "name": name,
                "rgb": list(rgb),
            }
            for cid, hex_val, name, max_de, rgb in palette_key
        ],
        "terminology": terms_payload,
        "version": version,
    }
    if triggers_key:
        payload["trigger_obligations"] = [
            {
                "id": tr_id,
                "min_font_height_ratio": min_fh,
                "required_disclaimer_id": req_id,
                "required_disclaimer_text": req_txt,
                "same_font_family": same_ff,
                "same_language": same_lang,
                "severity": sev,
                "trigger_pattern": trig_pat,
            }
            for tr_id, trig_pat, req_id, req_txt, same_lang, same_ff, min_fh, sev in triggers_key
        ]
    if voice_key is not None:
        vid, max_w, min_w, max_pas, max_fk, exs, min_sim, sev = voice_key
        payload["voice_profile"] = {
            "approved_exemplars": list(exs),
            "id": vid,
            "max_flesch_kincaid_grade": max_fk,
            "max_passive_voice_pct": max_pas,
            "max_sentence_words": max_w,
            "min_exemplar_similarity": min_sim,
            "min_sentence_words": min_w,
            "severity": sev,
        }
    if logos_key:
        payload["logos"] = [
            {
                "aspect_ratio": ar,
                "clear_space_ratio_h": cs_r,
                "id": lid,
                "max_aspect_distortion_pct": max_ad,
                "min_orb_matches": min_orb,
                "name": lname,
                "reference_path": ref_p,
                "severity": sev,
            }
            for lid, lname, ref_p, ar, max_ad, cs_r, min_orb, sev in logos_key
        ]
    if require_image_alt:
        payload["require_image_alt"] = True

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return CanonHash(hashlib.sha256(raw.encode("utf-8")).hexdigest())


# ── Canon ────────────────────────────────────────────────────────────


class Canon(FrozenModel, frozen=True):
    """The complete, immutable brand rule set. Versioned and content-hashed."""

    id: str
    version: str
    terminology: tuple[TermRule, ...] = ()
    palette: tuple[ColorToken, ...] = ()
    facts: tuple[FactClaim, ...] = ()
    trigger_obligations: tuple[TriggerObligation, ...] = ()
    voice_profile: VoiceProfile | None = None
    logos: tuple[LogoToken, ...] = ()
    require_image_alt: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hash(self) -> CanonHash:
        """Deterministic O(1)-cached hash of the entire rule set (canonical JSON, sorted keys)."""
        terms_key = tuple(
            (t.id, t.pattern_text, t.preferred, t.severity, t.note, t.pos_constraint)
            for t in self.terminology
        )
        palette_key = tuple((c.id, c.hex, c.name, c.max_delta_e, c.rgb) for c in self.palette)
        facts_key = tuple(
            (
                f.id,
                f.text,
                tuple(f.conditions),
                f.valid_until,
                f.subject_product,
                f.metric_value,
                f.comparison_operator,
                f.kfs_acceptance_validity_days,
                f.substantiation_level,
            )
            for f in self.facts
        )
        triggers_key = tuple(
            (
                tr.id,
                tr.trigger_pattern,
                tr.required_disclaimer_id,
                tr.required_disclaimer_text,
                tr.same_language,
                tr.same_font_family,
                tr.min_font_height_ratio,
                tr.severity,
            )
            for tr in self.trigger_obligations
        )
        vp = self.voice_profile
        voice_key: _VoiceHashKey = (
            (
                vp.id,
                vp.max_sentence_words,
                vp.min_sentence_words,
                vp.max_passive_voice_pct,
                vp.max_flesch_kincaid_grade,
                tuple(vp.approved_exemplars),
                vp.min_exemplar_similarity,
                vp.severity,
            )
            if vp is not None
            else None
        )
        logos_key = tuple(
            (
                lg.id,
                lg.name,
                lg.reference_path,
                lg.aspect_ratio,
                lg.max_aspect_distortion_pct,
                lg.clear_space_ratio_h,
                lg.min_orb_matches,
                lg.severity,
            )
            for lg in self.logos
        )
        return _compute_canon_hash_cached(
            self.id,
            self.version,
            terms_key,
            palette_key,
            facts_key,
            triggers_key,
            voice_key,
            logos_key,
            self.require_image_alt,
        )

    def __len__(self) -> int:
        extra = (
            (1 if self.voice_profile is not None else 0)
            + len(self.trigger_obligations)
            + len(self.logos)
        )
        return len(self.terminology) + len(self.palette) + len(self.facts) + extra

    def __iter__(self) -> Iterator[CanonRule]:  # type: ignore[override]
        yield from self.terminology
        yield from self.palette
        yield from self.facts
        yield from self.trigger_obligations
        if self.voice_profile is not None:
            yield self.voice_profile
        yield from self.logos

    def __contains__(self, rule_id: object) -> bool:
        if not isinstance(rule_id, str):
            return False
        return any(r.id == rule_id for r in self)

    def __getitem__(self, rule_id: str) -> CanonRule:
        """Look up any rule by id across all rule types."""
        for rule in self:
            if rule.id == rule_id:
                return rule
        raise KeyError(f"Rule {rule_id!r} not found in Canon {self.id}")

    def term_rules(self) -> tuple[TermRule, ...]:
        return self.terminology

    def color_tokens(self) -> tuple[ColorToken, ...]:
        return self.palette

    def to_rule_ref(self, rule: CanonRule) -> Rule:
        """Build a Rule reference from a concrete rule, for use in findings."""
        return rule.to_rule_ref()
