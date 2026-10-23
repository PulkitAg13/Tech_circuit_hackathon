"""Tier 1 Deterministic Check: ASCI 26px Disclaimer Height & CCPA Hindi-English Script Parity.

Enforces two Indian regulatory requirements (Named Improvement #3):
1. **ASCI Digital Media Disclaimer Guidelines:** Disclaimers in the bottom
   banner zone ($y \\ge 0.78 H$) must scale proportionally with image height
   ($\\ge 26\\text{px}$ at $1080\\text{p}$, i.e., $\\ge 2.4\\%$ of $H$, with an
   absolute legible floor of $12\\text{px}$ on standard web banners).
2. **CCPA 2022 Misleading Advertisement Guidelines (Clause 11):** Disclaimers
   must be in the same language/script as the primary claim. Flags a Blocker
   (`script_mismatch=True`, `severity=75`) when a Devanagari (Hindi) headline
   is paired with a Latin-only (English) disclaimer/footnote (`*T&C Apply`).
"""

from __future__ import annotations

import re
from typing import ClassVar

from canongate.checks._vision import detect_text_band_boxes, load_rgb_image
from canongate.domain.ast import ImageNode, Node, NodeKind, TextNode
from canongate.domain.canon import Canon, Rule
from canongate.domain.finding import (
    Finding,
    LegibilityEvidence,
    Span,
    Tier,
    Trace,
)
from canongate.engine.check import Check

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_DISCLAIMER_SPLIT_RE = re.compile(
    r"(?:\|\s*Footnote\s*:|\*(?:T&C|Terms|Conditions|Disclaimer)|"
    r"\b(?:Disclaimer|Note|T&C\s+Apply)\s*:)",
    re.IGNORECASE,
)


def _has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text))


def _has_latin(text: str) -> bool:
    return bool(_LATIN_WORD_RE.search(text))


class LegibilityPlacementCheck(Check):
    check_id: ClassVar[str] = "legibility.placement"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.IMAGE, NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        if isinstance(node, TextNode):
            return self._check_script_parity(node)
        if isinstance(node, ImageNode):
            return self._check_banner_legibility(node)
        return []

    def _check_script_parity(self, node: TextNode) -> list[Finding]:
        match = _DISCLAIMER_SPLIT_RE.search(node.text)
        if match is None:
            return []

        claim_part = node.text[: match.start()]
        disclaimer_part = node.text[match.start() :]

        claim_hi = _has_devanagari(claim_part)
        disc_hi = _has_devanagari(disclaimer_part)
        disc_lat = _has_latin(disclaimer_part)

        # CCPA 2022 Clause 11: Hindi/Devanagari claim paired with English-only disclaimer
        if (claim_hi and not disc_hi and disc_lat) or (
            not claim_hi and _has_latin(claim_part) and disc_hi and not disc_lat
        ):
            rule_ref = Rule(
                rule_id="ccpa-2022-clause-11-script-parity",
                rule_type="legibility",
                source_text=(
                    "CCPA 2022 Clause 11: A disclaimer shall be in the same language/script "
                    "as the primary claim of the advertisement."
                ),
            )
            span = Span(start=match.start(), end=len(node.text))
            return [
                self.finding(
                    node=node,
                    locator=span,
                    severity=75,
                    message=(
                        "CCPA 2022 Clause 11 script mismatch: primary claim and disclaimer "
                        "use different scripts (Devanagari vs Latin)."
                    ),
                    rule_ref=rule_ref,
                    evidence=LegibilityEvidence(
                        measured_box_px=0.0,
                        estimated_x_height_px=0.0,
                        required_px=26.0,
                        image_height_px=0,
                        ocr_confidence=1.0,
                        script_mismatch=True,
                    ),
                    trace=Trace(tier=Tier.DETERMINISTIC),
                )
            ]
        return []

    def _check_banner_legibility(self, node: ImageNode) -> list[Finding]:
        rgb_img = load_rgb_image(node.asset_path)
        if rgb_img is None:
            return []

        h, w, _ = rgb_img.shape
        # Only enforce ASCI 26px/1080p proportional height on banners >= 300px tall
        if h < 300 or w < 200:
            return []

        required_px = round(max(12.0, 26.0 * (h / 1080.0)), 1)
        rule_ref = Rule(
            rule_id="asci-disclaimer-26px",
            rule_type="legibility",
            source_text=(
                "ASCI Digital Disclaimer Guidelines: disclaimer text height must be >= "
                "26px at 1080p (2.4% of vertical height)."
            ),
        )

        findings: list[Finding] = []
        for box in detect_text_band_boxes(rgb_img):
            # Bottom 22% of banner is the fine-print disclaimer zone
            if box.y >= int(h * 0.78) and box.h < required_px:
                est_x_height = round(box.h * 0.52, 2)
                findings.append(
                    self.finding(
                        node=node,
                        locator=box,
                        severity=70,
                        message=(
                            f"Disclaimer text height ({box.h}px, x-height ~{est_x_height}px) "
                            f"is below ASCI minimum {required_px}px for a {h}px-tall banner."
                        ),
                        rule_ref=rule_ref,
                        evidence=LegibilityEvidence(
                            measured_box_px=float(box.h),
                            estimated_x_height_px=est_x_height,
                            required_px=required_px,
                            image_height_px=h,
                            ocr_confidence=0.92,
                            script_mismatch=False,
                        ),
                        trace=Trace(tier=Tier.DETERMINISTIC),
                    )
                )
        return findings
