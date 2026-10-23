"""Canon loading, compilation (Pipeline A), linting, and v1.1 impact simulation."""

from canongate.canon.compiler import (
    AnchorAuditResult,
    CanonCompiler,
    GroundedRuleRecord,
    audit_and_repair_fact_claim,
    compile_canon,
    extract_restrictive_qualifiers,
    extract_value_anchors,
    ground_char_interval,
    reconstruct_rule_prose,
    verify_round_trip_nli,
)
from canongate.canon.impact import (
    CanonLintIssue,
    CanonRevisionProposal,
    ImpactSimulationResult,
    RuleRevisionDiff,
    lint_canon,
    propose_canon_revision,
    simulate_canon_impact,
)
from canongate.canon.loader import load_canon

__all__ = [
    "AnchorAuditResult",
    "CanonCompiler",
    "CanonLintIssue",
    "CanonRevisionProposal",
    "GroundedRuleRecord",
    "ImpactSimulationResult",
    "RuleRevisionDiff",
    "audit_and_repair_fact_claim",
    "compile_canon",
    "extract_restrictive_qualifiers",
    "extract_value_anchors",
    "ground_char_interval",
    "lint_canon",
    "load_canon",
    "propose_canon_revision",
    "reconstruct_rule_prose",
    "simulate_canon_impact",
    "verify_round_trip_nli",
]
