"""Finding: what the engine says about a piece of content.

Each finding has:
- A stable id (deterministic from check + content + location)
- Typed evidence (discriminated union → exhaustive UI rendering)
- A trace (tier, AI used, model SHA, latency — for Context Trace badges)
- An optional suggestion (never auto-applied)
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field

from canongate.domain.canon import Rule
from canongate.domain.types import FindingId, NodeId

# ── Locators ─────────────────────────────────────────────────────────


class Span(BaseModel, frozen=True):
    """Character-level span within a TextNode, [start, end)."""

    start: int
    end: int

    def __len__(self) -> int:
        return self.end - self.start

    def __contains__(self, i: int) -> bool:
        return self.start <= i < self.end

    @property
    def key(self) -> str:
        return f"s:{self.start}-{self.end}"


class BBox(BaseModel, frozen=True):
    """Pixel-level bounding box within an ImageNode."""

    x: int
    y: int
    w: int
    h: int

    @property
    def key(self) -> str:
        return f"b:{self.x},{self.y},{self.w},{self.h}"


Locator = Span | BBox


# ── Evidence types (discriminated union) ─────────────────────────────


class TermMatch(BaseModel, frozen=True):
    """Evidence: a banned term was found."""

    kind: Literal["term_match"] = "term_match"
    term: str
    preferred: str


class ColorDistance(BaseModel, frozen=True):
    """Evidence: a colour drifted beyond the allowed ΔE00."""

    kind: Literal["color_distance"] = "color_distance"
    found_hex: str
    approved_hex: str
    delta_e: float
    max_allowed: float


# Add new evidence types here as the system grows.
# Each new type = one new model here + one new React component in features/findings/evidence/

Evidence = Annotated[TermMatch | ColorDistance, Field(discriminator="kind")]


# ── Suggestion ───────────────────────────────────────────────────────


class Replace(BaseModel, frozen=True):
    """A suggested text replacement for a span."""

    span: Span
    replacement: str


class Suggestion(BaseModel, frozen=True):
    """An engine-proposed fix. Never auto-applied."""

    label: str
    replacements: tuple[Replace, ...] = ()


# ── Tier and Verdict ─────────────────────────────────────────────────


class Tier(StrEnum):
    DETERMINISTIC = "deterministic"  # Tier 1: zero AI
    SMT = "smt"  # Tier 1.5: solver proof
    NLI = "nli"  # Tier 2: calibrated model
    GENERATIVE = "generative"  # Tier 3: constrained rewriter


class Verdict(IntEnum):
    PASS = 0
    WARNING = 1
    BLOCKER = 2

    @classmethod
    def from_severity(cls, severity: int) -> Verdict:
        if severity == 0:
            return cls.PASS
        if severity < 50:
            return cls.WARNING
        return cls.BLOCKER


# ── Trace ────────────────────────────────────────────────────────────


class Trace(BaseModel, frozen=True):
    """Context Trace: how a finding was produced. Shown on every finding card."""

    tier: Tier
    ai_used: bool = False
    external_call: bool = False
    model_sha: str | None = None
    latency_ms: float | None = None


# ── Finding ──────────────────────────────────────────────────────────


class Finding(BaseModel, frozen=True):
    """A single issue found in a content node."""

    id: FindingId
    check_id: str
    node_id: NodeId
    locator: Locator
    severity: Annotated[int, Field(ge=0, le=100)]
    message: str
    rule_ref: Rule
    evidence: Evidence
    suggestion: Suggestion | None = None
    trace: Trace

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verdict(self) -> Verdict:
        return Verdict.from_severity(self.severity)
