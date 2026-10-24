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

from pydantic import Field

from canongate.domain.canon import Rule
from canongate.domain.types import FindingId, FrozenModel, NodeId, computed_field

# ── Locators ─────────────────────────────────────────────────────────


class Span(FrozenModel, frozen=True):
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


class BBox(FrozenModel, frozen=True):
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


class TermMatch(FrozenModel, frozen=True):
    """Evidence: a banned term was found."""

    kind: Literal["term_match"] = "term_match"
    term: str
    preferred: str


class ColorDistance(FrozenModel, frozen=True):
    """Evidence: a colour drifted beyond the allowed ΔE00."""

    kind: Literal["color_distance"] = "color_distance"
    found_hex: str
    approved_hex: str
    delta_e: float
    max_allowed: float


class ContrastEvidence(FrozenModel, frozen=True):
    """Evidence: WCAG 2.1 AA/AAA relative luminance contrast failure."""

    kind: Literal["contrast"] = "contrast"
    fg_hex: str
    bg_hex: str
    contrast_ratio: float
    required_ratio: float
    wcag_level: Literal["AA", "AAA"] = "AA"
    suggested_fg_hex: str | None = None


class LegibilityEvidence(FrozenModel, frozen=True):
    """Evidence: ASCI 26px / x-height or CCPA disclaimer legibility violation."""

    kind: Literal["legibility"] = "legibility"
    measured_box_px: float
    estimated_x_height_px: float
    required_px: float
    image_height_px: int
    ocr_confidence: float
    script_mismatch: bool = False


class SaliencyEvidence(FrozenModel, frozen=True):
    """Evidence: visual subordination of a disclaimer relative to headline claim."""

    kind: Literal["saliency"] = "saliency"
    disclaimer_saliency: float
    headline_saliency: float
    ratio: float
    min_ratio: float = 0.25


class ConfusableEvidence(FrozenModel, frozen=True):
    """Evidence: Unicode UTS #39 homoglyph or mixed-script spoofing detected."""

    kind: Literal["confusable"] = "confusable"
    spoofed_token: str
    normalized_token: str
    confusable_chars: tuple[str, ...] = ()
    scripts_detected: tuple[str, ...] = ()


class AlgebraicProofEvidence(FrozenModel, frozen=True):
    """Evidence: Z3 SMT solver counterexample or contradiction proof."""

    kind: Literal["algebraic_proof"] = "algebraic_proof"
    draft_expr: str
    canon_constraint: str
    solver_status: Literal["sat_counterexample", "unsat_valid"]
    counterexample: dict[str, str] = Field(default_factory=dict)


class SlotEntry(FrozenModel, frozen=True):
    """Single predicate-argument slot comparison entry."""

    slot: str
    canon_value: str
    draft_value: str
    status: Literal["match", "dropped", "contradicted", "unverified"]


class SlotDiffEvidence(FrozenModel, frozen=True):
    """Evidence: MiniCheck NLI entailment probability and slot-level alignment."""

    kind: Literal["slot_diff"] = "slot_diff"
    entailment_prob: float
    canon_claim_id: str
    canon_text: str
    slots: tuple[SlotEntry, ...] = ()


class C2paEvidence(FrozenModel, frozen=True):
    """Evidence: C2PA JUMBF Content Credentials provenance state."""

    kind: Literal["c2pa"] = "c2pa"
    has_manifest: bool
    validation_state: str
    issuer: str | None = None
    digital_source_type: str | None = None


class HiddenTextEvidence(FrozenModel, frozen=True):
    """Evidence: OWASP LLM01 indirect prompt injection or hidden text."""

    kind: Literal["hidden_text"] = "hidden_text"
    mechanism: str
    extracted_snippet: str


class LogoGeometryEvidence(FrozenModel, frozen=True):
    """Evidence: OpenCV ORB logo aspect distortion (<= 2%) or 0.5H clear-space intrusion."""

    kind: Literal["logo_geometry"] = "logo_geometry"
    logo_id: str
    expected_aspect_ratio: float
    detected_aspect_ratio: float
    aspect_distortion_pct: float
    max_aspect_distortion_pct: float
    clear_space_ratio_h: float
    clear_space_intrusion_pct: float
    orb_inlier_matches: int = 0


class VoiceReadabilityEvidence(FrozenModel, frozen=True):
    """Evidence: VoiceProfile sentence-length, passive-voice %, and Flesch-Kincaid bounds."""

    kind: Literal["voice_readability"] = "voice_readability"
    flesch_kincaid_grade: float
    max_flesch_kincaid_grade: float
    passive_voice_pct: float
    max_passive_voice_pct: float
    max_sentence_words_observed: int
    max_sentence_words_allowed: int
    exemplar_similarity: float = 1.0


class TriggerObligationEvidence(FrozenModel, frozen=True):
    """Evidence: missing or language-mismatched trigger disclaimer / creator disclosure."""

    kind: Literal["trigger_obligation"] = "trigger_obligation"
    obligation_id: str
    matched_trigger: str
    required_disclaimer_id: str
    required_disclaimer_text: str
    same_language_required: bool = True


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
    | HiddenTextEvidence
    | LogoGeometryEvidence
    | VoiceReadabilityEvidence
    | TriggerObligationEvidence,
    Field(discriminator="kind"),
]


# ── Suggestion ───────────────────────────────────────────────────────


class Replace(FrozenModel, frozen=True):
    """A suggested text replacement for a span."""

    span: Span
    replacement: str


class Suggestion(FrozenModel, frozen=True):
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


class Trace(FrozenModel, frozen=True):
    """Context Trace: how a finding was produced. Shown on every finding card."""

    tier: Tier
    ai_used: bool = False
    external_call: bool = False
    model_sha: str | None = None
    latency_ms: float | None = None


# ── Finding ──────────────────────────────────────────────────────────


class Finding(FrozenModel, frozen=True):
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
