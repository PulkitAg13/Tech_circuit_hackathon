"""Canon: the machine-readable representation of brand rules.

Loaded from YAML or compiled via Pipeline A (`CanonCompiler`).
Supports CanonGate rule schemas (`TermRule` with `pos_constraint`,
`ColorToken`, and `FactClaim` with `substantiation_level` and KFS metadata).
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
    """Compile a case-insensitive boundary regex for `pattern_text`.

    Uses standard `\\b` word boundaries when the leading/trailing character is
    alphanumeric (`\\w`), and lookaround boundaries `(?<!\\w)` / `(?!\\w)` when the
    leading/trailing character is a symbol (such as `%`, `₹`, `$`, `#`), avoiding
    the Python `re` trap where `\\b100%\\b` fails to match before whitespace.
    """
    if not pattern_text:
        return re.compile(r"(?!x)x")
    lead = r"\b" if (pattern_text[0].isalnum() or pattern_text[0] == "_") else r"(?<!\w)"
    tail = r"\b" if (pattern_text[-1].isalnum() or pattern_text[-1] == "_") else r"(?!\w)"
    return re.compile(f"{lead}{re.escape(pattern_text)}{tail}", re.IGNORECASE)


@lru_cache(maxsize=256)
def _parse_hex_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        raise ValueError(f"Invalid hex colour: {hex_str!r}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ── Rule models ──────────────────────────────────────────────────────


class TermRule(FrozenModel, frozen=True):
    """A banned term with its preferred replacement and optional POS constraint."""

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


class ColorToken(FrozenModel, frozen=True):
    """An approved brand colour with a maximum drift tolerance (CIEDE2000)."""

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


class FactClaim(FrozenModel, frozen=True):
    """An approved factual claim that content may reference (FactClaimSchema)."""

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


class Rule(FrozenModel, frozen=True):
    """Generic rule reference used in findings to point back at the Canon source."""

    rule_id: str
    rule_type: str  # "term", "color", "fact", etc.
    source_text: str = ""  # the raw text from the brand book, for explainability


CanonRule = TermRule | ColorToken | FactClaim

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


@lru_cache(maxsize=128)
def _compute_canon_hash_cached(
    canon_id: str,
    version: str,
    terms_key: tuple[_TermHashKey, ...],
    palette_key: tuple[_PaletteHashKey, ...],
    facts_key: tuple[_FactHashKey, ...],
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

    payload = {
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
        return _compute_canon_hash_cached(
            self.id,
            self.version,
            terms_key,
            palette_key,
            facts_key,
        )

    def __len__(self) -> int:
        return len(self.terminology) + len(self.palette) + len(self.facts)

    def __iter__(self) -> Iterator[CanonRule]:  # type: ignore[override]
        yield from self.terminology
        yield from self.palette
        yield from self.facts

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
        if isinstance(rule, TermRule):
            return Rule(
                rule_id=rule.id, rule_type="term", source_text=rule.note or rule.pattern_text
            )
        if isinstance(rule, ColorToken):
            return Rule(rule_id=rule.id, rule_type="color", source_text=str(rule))
        return Rule(rule_id=rule.id, rule_type="fact", source_text=rule.text)
