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

    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]

    def __init__(self, **data: object) -> None:
        super().__init__(**data)
        if self.end < self.start:
            raise ValueError(f"Span end ({self.end}) must be >= start ({self.start})")

    def __len__(self) -> int:
        return self.end - self.start

    def __bool__(self) -> bool:
        return self.end > self.start

    def __contains__(self, item: int | Span) -> bool:
        if isinstance(item, Span):
            return self.start <= item.start and item.end <= self.end
        return self.start <= item < self.end

    def __lt__(self, other: Span) -> bool:
        if not isinstance(other, Span):
            return NotImplemented
        return (self.start, self.end) < (other.start, other.end)

    def overlaps(self, other: Span) -> bool:
        """Return True if two non-empty spans overlap."""
        return max(self.start, other.start) < min(self.end, other.end)

    def slice(self, text: str) -> str:
        """Extract the substring covered by this span."""
        return text[self.start : self.end]

    @property
    def key(self) -> str:
        return f"s:{self.start}-{self.end}"

    @property
    def sort_key(self) -> tuple[int, int, int, int, int]:
        return (0, self.start, self.end, 0, 0)


class BBox(BaseModel, frozen=True):
    """Pixel-level bounding box within an ImageNode."""

    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]
    w: Annotated[int, Field(ge=0)]
    h: Annotated[int, Field(ge=0)]

    @property
    def area(self) -> int:
        return self.w * self.h

    def __bool__(self) -> bool:
        return self.w > 0 and self.h > 0

    def __contains__(self, item: tuple[int, int] | BBox) -> bool:
        if isinstance(item, BBox):
            return (
                self.x <= item.x
                and self.y <= item.y
                and item.x + item.w <= self.x + self.w
                and item.y + item.h <= self.y + self.h
            )
        px, py = item
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def __lt__(self, other: BBox) -> bool:
        if not isinstance(other, BBox):
            return NotImplemented
        return (self.y, self.x, self.w, self.h) < (other.y, other.x, other.w, other.h)

    @property
    def key(self) -> str:
        return f"b:{self.x},{self.y},{self.w},{self.h}"

    @property
    def sort_key(self) -> tuple[int, int, int, int, int]:
        return (1, self.y, self.x, self.w, self.h)


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


class ContrastEvidence(BaseModel, frozen=True):
    """Evidence: WCAG 2.1 AA/AAA relative luminance contrast failure."""

    kind: Literal["contrast"] = "contrast"
    fg_hex: str
    bg_hex: str
    contrast_ratio: float
    required_ratio: float
    wcag_level: Literal["AA", "AAA"] = "AA"
    suggested_fg_hex: str | None = None


class LegibilityEvidence(BaseModel, frozen=True):
    """Evidence: ASCI 26px / x-height or CCPA disclaimer legibility violation."""

    kind: Literal["legibility"] = "legibility"
    measured_box_px: float
    estimated_x_height_px: float
    required_px: float
    image_height_px: int
    ocr_confidence: float
    script_mismatch: bool = False


class SaliencyEvidence(BaseModel, frozen=True):
    """Evidence: visual subordination of a disclaimer relative to headline claim."""

    kind: Literal["saliency"] = "saliency"
    disclaimer_saliency: float
    headline_saliency: float
    ratio: float
    min_ratio: float = 0.25


class ConfusableEvidence(BaseModel, frozen=True):
    """Evidence: Unicode UTS #39 homoglyph or mixed-script spoofing detected."""

    kind: Literal["confusable"] = "confusable"
    spoofed_token: str
    normalized_token: str
    confusable_chars: tuple[str, ...] = ()
    scripts_detected: tuple[str, ...] = ()


class AlgebraicProofEvidence(BaseModel, frozen=True):
    """Evidence: Z3 SMT solver counterexample or contradiction proof."""

    kind: Literal["algebraic_proof"] = "algebraic_proof"
    draft_expr: str
    canon_constraint: str
    solver_status: Literal["sat_counterexample", "unsat_valid"]
    counterexample: dict[str, str] = Field(default_factory=dict)


class SlotEntry(BaseModel, frozen=True):
    """Single predicate-argument slot comparison entry."""

    slot: str
    canon_value: str
    draft_value: str
    status: Literal["match", "dropped", "contradicted", "unverified"]


class SlotDiffEvidence(BaseModel, frozen=True):
    """Evidence: MiniCheck NLI entailment probability and slot-level alignment."""

    kind: Literal["slot_diff"] = "slot_diff"
    entailment_prob: float
    canon_claim_id: str
    canon_text: str
    slots: tuple[SlotEntry, ...] = ()


class C2paEvidence(BaseModel, frozen=True):
    """Evidence: C2PA JUMBF Content Credentials provenance state."""

    kind: Literal["c2pa"] = "c2pa"
    has_manifest: bool
    validation_state: str
    issuer: str | None = None
    digital_source_type: str | None = None


class HiddenTextEvidence(BaseModel, frozen=True):
    """Evidence: OWASP LLM01 indirect prompt injection or hidden text."""

    kind: Literal["hidden_text"] = "hidden_text"
    mechanism: str
    extracted_snippet: str


Evidence = Annotated[
    TermMatch
    | ColorDistance
    | ContrastEvidence
    | LegibilityEvidence
    | SaliencyEvidence
    | ConfusableEvidence
    | AlgebraicProofEvidence
    | SlotDiffEvidence
    | C2paEvidence
    | HiddenTextEvidence,
    Field(discriminator="kind"),
]


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

    @property
    def is_blocker(self) -> bool:
        return self.verdict == Verdict.BLOCKER

    @property
    def is_warning(self) -> bool:
        return self.verdict == Verdict.WARNING

    def __lt__(self, other: Finding) -> bool:
        if not isinstance(other, Finding):
            return NotImplemented
        return (
            self.locator.sort_key,
            -self.severity,
            self.check_id,
            str(self.id),
        ) < (
            other.locator.sort_key,
            -other.severity,
            other.check_id,
            str(other.id),
        )
