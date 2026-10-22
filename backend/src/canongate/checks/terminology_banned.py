"""Terminology / Banned-Term Check (Tier 1 — deterministic, zero AI).

Scans every TextNode for patterns from the Canon's terminology rules.
Produces one Finding per match, with a Replace suggestion pointing to
the approved alternative.
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
from canongate.domain.types import stable_finding_id
from canongate.engine.check import Check


class TerminologyBannedCheck(Check):
    check_id: ClassVar[str] = "terminology.banned"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, TextNode)
        findings: list[Finding] = []

        for rule in canon.term_rules():
            for m in rule.pattern.finditer(node.text):
                span = Span(start=m.start(), end=m.end())
                fid = stable_finding_id(self.check_id, self.check_version, node.id, span.key)

                findings.append(
                    Finding(
                        id=fid,
                        check_id=self.check_id,
                        node_id=node.id,
                        locator=span,
                        severity=rule.severity,
                        message=f'Use "{rule.preferred}" instead of "{m.group()}"',
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
