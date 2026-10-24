"""Tier 1 Deterministic Check: Trigger Obligations & ASCI Influencer Upfront Disclosures.

Implements Round 1 Plan §1, §2 & §3.3 (`TriggerObligationSchema` + ASCI Influencer pack):
1. Evaluates `canon.trigger_obligations` (`IF trigger_pattern THEN required_disclaimer_text`,
   plus `same_language` parity between trigger claim and disclaimer).
2. Audits influencer/creator promotional posts for ASCI Guidelines for Influencer
   Advertising in Digital Media: when copy contains explicit creator sponsorship
   cues (`gifted by`, `paid collab`, `partnered with`, `#sponsoredpost`, `#influencer`,
   or promo code callouts like `use my code`), requires an upfront disclosure label
   (`#ad`, `#sponsored`, `#collab`, `Paid partnership`, `Advertisement`) within the
   opening 120 characters before any fold/truncation.
"""

from __future__ import annotations

import re
from typing import ClassVar

from canongate.checks.legibility_placement import _has_devanagari, _has_latin
from canongate.domain.ast import ContentAST, Node, NodeKind, TextNode
from canongate.domain.canon import Canon, Rule
from canongate.domain.finding import (
    Finding,
    Replace,
    Span,
    Suggestion,
    Tier,
    Trace,
    TriggerObligationEvidence,
)
from canongate.engine.check import Check

_INFLUENCER_CUE_RE = re.compile(
    r"(?:\b(?:gifted\s+by|paid\s+collab(?:oration)?|partnered\s+with|in\s+partnership\s+with|"
    r"use\s+my\s+(?:promo\s+)?code|link\s+in\s+my\s+bio\s+for\s+discount)\b|"
    r"#(?:influencer|brandambassador|sponsoredpost|gifted)\b)",
    re.IGNORECASE,
)
_UPFRONT_DISCLOSURE_RE = re.compile(
    r"(?:^|\s)(?:#(?:ad|sponsored|collab|partnership|paidpartnership)\b|"
    r"\b(?:paid\s+partnership|advertisement|sponsored\s+by)\b)",
    re.IGNORECASE,
)


def _detect_script_code(text: str) -> str:
    if _has_devanagari(text):
        return "hi"
    if _has_latin(text):
        return "en"
    return "und"


class TriggerDisclaimerCheck(Check):
    """Tier 1 check for `TriggerObligation` rules and ASCI Influencer upfront disclosures."""

    check_id: ClassVar[str] = "trigger.disclaimer"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})
    prefer_bundle: ClassVar[bool] = True

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        if not isinstance(node, TextNode):
            return []
        return self._evaluate_nodes([node], canon)

    def run_bundle(self, ast: ContentAST, canon: Canon) -> list[Finding]:
        text_nodes = [n for n in ast.of_kind(NodeKind.TEXT) if isinstance(n, TextNode)]
        if not text_nodes:
            return []
        return self._evaluate_nodes(text_nodes, canon)

    def _evaluate_nodes(
        self,
        text_nodes: list[TextNode],
        canon: Canon,
    ) -> list[Finding]:
        findings: list[Finding] = []
        full_bundle_text = "\n".join(n.text for n in text_nodes)
        full_bundle_lower = full_bundle_text.lower()

        # 1. Canon TriggerObligationSchema rules
        for obl in canon.trigger_obligations:
            for node in text_nodes:
                match = obl.pattern.search(node.text)
                if match is None:
                    continue

                req_text = obl.required_disclaimer_text.strip()
                has_disclaimer = bool(req_text and req_text.lower() in full_bundle_lower)
                claim_lang = _detect_script_code(node.text)
                disc_lang = _detect_script_code(req_text) if req_text else claim_lang
                lang_mismatch = (
                    obl.same_language
                    and has_disclaimer
                    and claim_lang != "und"
                    and disc_lang != "und"
                    and claim_lang != disc_lang
                )

                if not has_disclaimer or lang_mismatch:
                    span = Span(start=match.start(), end=match.end())
                    appended = f"{node.text.rstrip()} ({req_text})"
                    reason = (
                        f"Missing required trigger disclaimer {req_text!r} "
                        f"for trigger phrase {match.group(0)!r}."
                        if not has_disclaimer
                        else (
                            f"Trigger disclaimer language ({disc_lang}) does not match "
                            f"claim language ({claim_lang})."
                        )
                    )
                    findings.append(
                        self.finding(
                            node=node,
                            locator=span,
                            severity=obl.severity,
                            message=reason,
                            rule_ref=obl.to_rule_ref(),
                            evidence=TriggerObligationEvidence(
                                obligation_id=obl.id,
                                matched_trigger=match.group(0),
                                required_disclaimer_id=obl.required_disclaimer_id,
                                required_disclaimer_text=req_text,
                                same_language_required=obl.same_language,
                            ),
                            suggestion=(
                                Suggestion(
                                    label=(
                                        f"Append required disclaimer ({obl.required_disclaimer_id})"
                                    ),
                                    replacements=(
                                        Replace(
                                            span=Span(start=0, end=len(node.text)),
                                            replacement=appended,
                                        ),
                                    ),
                                )
                                if req_text
                                else None
                            ),
                            trace=Trace(tier=Tier.DETERMINISTIC),
                        )
                    )
                    break

        # 2. ASCI Influencer Guidelines upfront disclosure check
        asci_rule = Rule(
            rule_id="asci-influencer-upfront-disclosure",
            rule_type="trigger_obligation",
            source_text=(
                "ASCI Influencer Guidelines: promotional creator posts must carry an "
                "upfront disclosure label (#ad, #sponsored, #collab, or Paid partnership) "
                "in the first two lines before any truncation fold."
            ),
        )
        for node in text_nodes:
            cue = _INFLUENCER_CUE_RE.search(node.text)
            if cue is None:
                continue
            opening_window = node.text[:120]
            if _UPFRONT_DISCLOSURE_RE.search(opening_window) is None:
                findings.append(
                    self.finding(
                        node=node,
                        locator=Span(start=cue.start(), end=cue.end()),
                        severity=70,
                        message=(
                            "ASCI Influencer disclosure failure: promotional post contains "
                            f"{cue.group(0)!r} without an upfront '#ad' or 'Paid partnership' "
                            "disclosure label in the opening lines."
                        ),
                        rule_ref=asci_rule,
                        evidence=TriggerObligationEvidence(
                            obligation_id="asci-influencer-upfront-disclosure",
                            matched_trigger=cue.group(0),
                            required_disclaimer_id="asci-upfront-ad-label",
                            required_disclaimer_text="#ad | Paid partnership",
                            same_language_required=True,
                        ),
                        suggestion=Suggestion(
                            label="Prepend upfront '#ad' disclosure",
                            replacements=(
                                Replace(
                                    span=Span(start=0, end=len(node.text)),
                                    replacement=f"#ad {node.text}",
                                ),
                            ),
                        ),
                        trace=Trace(tier=Tier.DETERMINISTIC),
                    )
                )

        return findings
