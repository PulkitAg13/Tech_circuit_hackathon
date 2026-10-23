"""Canon loading, compilation (Pipeline A), and anti-loss guards."""

from canongate.canon.compiler import (
    AnchorAuditResult,
    CanonCompiler,
    GroundedRuleRecord,
    audit_and_repair_fact_claim,
    compile_canon,
    extract_restrictive_qualifiers,
    extract_value_anchors,
    ground_char_interval,
)
from canongate.canon.loader import load_canon

__all__ = [
    "AnchorAuditResult",
    "CanonCompiler",
    "GroundedRuleRecord",
    "audit_and_repair_fact_claim",
    "compile_canon",
    "extract_restrictive_qualifiers",
    "extract_value_anchors",
    "ground_char_interval",
    "load_canon",
]
