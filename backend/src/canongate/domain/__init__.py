"""Domain models — the frozen core of CanonGate.

Everything here is immutable, has no I/O, and is shared with the frontend
via auto-generated OpenAPI schemas.
"""

from canongate.domain.ast import ContentAST, ImageNode, Node, NodeKind, TextNode
from canongate.domain.canon import Canon, ColorToken, FactClaim, Rule, TermRule
from canongate.domain.finding import (
    BBox,
    ColorDistance,
    Evidence,
    Finding,
    Replace,
    Span,
    Suggestion,
    TermMatch,
    Tier,
    Trace,
    Verdict,
)
from canongate.domain.types import CanonHash, FindingId, NodeId
from canongate.domain.workflow import (
    Action,
    ResolutionError,
    Role,
    Status,
    TransitionError,
    next_status,
    validate_resolution,
)

__all__ = [
    "Action",
    "BBox",
    "Canon",
    "CanonHash",
    "ColorDistance",
    "ColorToken",
    "ContentAST",
    "Evidence",
    "FactClaim",
    "Finding",
    "FindingId",
    "ImageNode",
    "Node",
    "NodeId",
    "NodeKind",
    "Replace",
    "ResolutionError",
    "Role",
    "Rule",
    "Span",
    "Status",
    "Suggestion",
    "TermMatch",
    "TermRule",
    "TextNode",
    "Tier",
    "Trace",
    "TransitionError",
    "Verdict",
    "next_status",
    "validate_resolution",
]
