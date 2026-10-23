"""Tier 1 Deterministic Check: Hidden Text & OWASP LLM01 Indirect Prompt Injection.

Detects:
1. `TextNode`s isolated onto `{source}/hidden[{i}]` or `{source}/page[{p}]/hidden[{i}]`
   AST paths by `parse_html` (CSS `display:none`, `visibility:hidden`, `opacity:0`,
   `font-size:0`, white-on-white) or `parse_pdf` (`< 4pt` micro-font or white-on-white).
2. Inline CSS hiding declarations (`display: none`, `font-size: 0`, `opacity: 0`,
   or identical foreground/background colour hex) in raw text/markup.
3. OWASP LLM01 adversarial prompt-injection instructions (`"Ignore all previous
   compliance rules..."`, `"Disregard prior instructions..."`, `"Mark this
   submission APPROVED"`).
"""

from __future__ import annotations

import re
from typing import ClassVar

from canongate.domain.ast import Node, NodeKind, TextNode
from canongate.domain.canon import Canon, Rule
from canongate.domain.finding import (
    Finding,
    HiddenTextEvidence,
    Replace,
    Span,
    Suggestion,
    Tier,
    Trace,
)
from canongate.engine.check import Check

_PROMPT_INJECTION_RE = re.compile(
    r"(?:"
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+"
    r"(?:compliance\s+)?(?:rules|instructions|prompts)|"
    r"disregard\s+(?:all\s+)?(?:previous|prior)\s+(?:rules|instructions)|"
    r"system\s+prompt\s*:|"
    r"mark\s+(?:this\s+)?(?:submission|content|draft)\s+(?:as\s+)?approved"
    r")",
    re.IGNORECASE,
)

_CSS_CLOAK_RE = re.compile(
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?\b|"
    r"font-size\s*:\s*0(?:px|pt|em|rem|%)?\b|"
    r"color\s*:\s*(#[0-9A-Fa-f]{3,6})\b[^;\n]*;\s*(?:background-color|background)\s*:\s*\1\b)",
    re.IGNORECASE,
)


class SecurityHiddenTextCheck(Check):
    check_id: ClassVar[str] = "security.hidden_text"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, TextNode)
        rule_ref = Rule(
            rule_id="owasp-llm01-hidden-text",
            rule_type="security",
            source_text=(
                "OWASP LLM01 / ASCI Dark Patterns: hidden micro-text, zero-contrast cloaking, "
                "and indirect prompt-injection directives are prohibited."
            ),
        )

        # Case 1: Node was already isolated onto a */hidden[*] path by parse_html or parse_pdf
        if "/hidden[" in node.path:
            is_inj = bool(_PROMPT_INJECTION_RE.search(node.text))
            mechanism = (
                "css_or_pdf_hidden_prompt_injection"
                if is_inj
                else "css_or_pdf_hidden_node"
            )
            full_span = Span(start=0, end=len(node.text))
            return [
                self.finding(
                    node=node,
                    locator=full_span,
                    severity=95,
                    message=(
                        f"Hidden text block detected at {node.path} ({mechanism}): "
                        f"{node.text[:80]!r}"
                    ),
                    rule_ref=rule_ref,
                    evidence=HiddenTextEvidence(
                        mechanism=mechanism,
                        extracted_snippet=node.text[:200],
                    ),
                    suggestion=Suggestion(
                        label="Remove hidden text block",
                        replacements=(Replace(span=full_span, replacement=""),),
                    ),
                    trace=Trace(tier=Tier.DETERMINISTIC),
                )
            ]

        findings: list[Finding] = []

        # Case 2: Adversarial prompt-injection directives in visible or raw text
        for match in _PROMPT_INJECTION_RE.finditer(node.text):
            span = Span(start=match.start(), end=match.end())
            snippet = match.group(0)
            findings.append(
                self.finding(
                    node=node,
                    locator=span,
                    severity=95,
                    message=f"OWASP LLM01 prompt-injection directive detected: {snippet!r}",
                    rule_ref=rule_ref,
                    evidence=HiddenTextEvidence(
                        mechanism="owasp_llm01_prompt_injection",
                        extracted_snippet=snippet,
                    ),
                    suggestion=Suggestion(
                        label="Strip prompt-injection directive",
                        replacements=(Replace(span=span, replacement=""),),
                    ),
                    trace=Trace(tier=Tier.DETERMINISTIC),
                )
            )

        # Case 3: Inline CSS cloaking in raw text/markup
        for match in _CSS_CLOAK_RE.finditer(node.text):
            span = Span(start=match.start(), end=match.end())
            snippet = match.group(0)
            findings.append(
                self.finding(
                    node=node,
                    locator=span,
                    severity=90,
                    message=f"Inline CSS text-hiding directive detected: {snippet!r}",
                    rule_ref=rule_ref,
                    evidence=HiddenTextEvidence(
                        mechanism="inline_css_cloaking",
                        extracted_snippet=snippet,
                    ),
                    suggestion=Suggestion(
                        label="Remove CSS text-hiding style",
                        replacements=(Replace(span=span, replacement=""),),
                    ),
                    trace=Trace(tier=Tier.DETERMINISTIC),
                )
            )

        return findings
