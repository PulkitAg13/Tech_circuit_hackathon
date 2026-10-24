"""Terminology / Banned-Term Check (Tier 1 — deterministic + spaCy POS constraints).

Scans every TextNode for patterns from the Canon's terminology rules.
When `TermRule.pos_constraint` is specified (e.g. `"NOUN"`, `"VERB"`, `"ADJ"`),
verifies via `SpacyLinguisticAnalyzer` that the matched span has the required
part-of-speech tag in sentence context.
"""

from __future__ import annotations

from typing import ClassVar

from canongate.domain.ast import Node, NodeKind, TextNode
from canongate.domain.canon import Canon
from canongate.domain.finding import (
    Finding,
    Replace,
    Span,
    Suggestion,
    TermMatch,
    Tier,
    Trace,
)
from canongate.engine.check import Check
from canongate.engine.nlp import default_linguistic_analyzer


class TerminologyBannedCheck(Check):
    check_id: ClassVar[str] = "terminology.banned"
    check_version: ClassVar[str] = "1.1"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, TextNode)
        findings: list[Finding] = []

        for rule in canon.term_rules():
            for m in rule.pattern.finditer(node.text):
                if rule.pos_constraint and not default_linguistic_analyzer.matches_pos_constraint(
                    node.text, m.start(), m.end(), rule.pos_constraint
                ):
                    continue

                span = Span(start=m.start(), end=m.end())
                findings.append(
                    self.finding(
                        node=node,
                        locator=span,
                        message=f'Use "{rule.preferred}" instead of "{m.group()}"',
                        severity=rule.severity,
                        rule_ref=canon.to_rule_ref(rule),
                        evidence=TermMatch(term=m.group(), preferred=rule.preferred),
                        suggestion=Suggestion(
                            label=f'Replace with "{rule.preferred}"',
                            replacements=(Replace(span=span, replacement=rule.preferred),),
                        ),
                        trace=Trace(tier=Tier.DETERMINISTIC),
                    )
                )

        return findings
