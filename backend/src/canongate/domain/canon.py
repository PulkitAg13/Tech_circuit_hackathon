"""Canon: the machine-readable representation of brand rules.

Today loaded from YAML. Later, Pipeline A will compile it from PDFs/DOCXs.
The engine only sees this model, so the compilation path is pluggable.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated

from pydantic import BaseModel, Field, computed_field

from canongate.domain.types import CanonHash

# ── Rule models ──────────────────────────────────────────────────────


class TermRule(BaseModel, frozen=True):
    """A banned term with its preferred replacement."""

    id: str
    pattern_text: str  # raw string, compiled into a regex at runtime
    preferred: str
    severity: Annotated[int, Field(ge=1, le=100)] = 60
    note: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pattern(self) -> re.Pattern[str]:
        # Word-boundary match, case-insensitive
        return re.compile(rf"\b{re.escape(self.pattern_text)}\b", re.IGNORECASE)

    model_config = {"arbitrary_types_allowed": True}


class ColorToken(BaseModel, frozen=True):
    """An approved brand colour with a maximum drift tolerance (CIEDE2000)."""

    id: str
    hex: str  # e.g. "#1A2B3C"
    name: str = ""
    max_delta_e: float = 3.0  # maximum ΔE00 before a Warning

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rgb(self) -> tuple[int, int, int]:
        h = self.hex.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class FactClaim(BaseModel, frozen=True):
    """An approved factual claim that content may reference."""

    id: str
    text: str
    conditions: list[str] = []
    valid_until: str | None = None  # ISO date


class Rule(BaseModel, frozen=True):
    """Generic rule reference used in findings to point back at the Canon source."""

    rule_id: str
    rule_type: str  # "term", "color", "fact", etc.
    source_text: str = ""  # the raw text from the brand book, for explainability


# ── Canon ────────────────────────────────────────────────────────────


class Canon(BaseModel, frozen=True):
    """The complete, immutable brand rule set. Versioned and content-hashed."""

    id: str
    version: str
    terminology: tuple[TermRule, ...] = ()
    palette: tuple[ColorToken, ...] = ()
    facts: tuple[FactClaim, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hash(self) -> CanonHash:
        """Deterministic hash of the entire rule set (canonical JSON, sorted keys)."""
        payload = self.model_dump(mode="json", exclude={"hash"})
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return CanonHash(hashlib.sha256(raw.encode()).hexdigest())

    def __getitem__(self, rule_id: str) -> TermRule | ColorToken | FactClaim:
        """Look up any rule by id across all rule types."""
        for collection in (self.terminology, self.palette, self.facts):
            for rule in collection:
                if rule.id == rule_id:
                    return rule
        raise KeyError(f"Rule {rule_id!r} not found in Canon {self.id}")

    def term_rules(self) -> tuple[TermRule, ...]:
        return self.terminology

    def color_tokens(self) -> tuple[ColorToken, ...]:
        return self.palette

    def to_rule_ref(self, rule: TermRule | ColorToken | FactClaim) -> Rule:
        """Build a Rule reference from a concrete rule, for use in findings."""
        if isinstance(rule, TermRule):
            return Rule(
                rule_id=rule.id, rule_type="term", source_text=rule.note or rule.pattern_text
            )
        if isinstance(rule, ColorToken):
            return Rule(rule_id=rule.id, rule_type="color", source_text=f"{rule.name} ({rule.hex})")
        return Rule(rule_id=rule.id, rule_type="fact", source_text=rule.text)
