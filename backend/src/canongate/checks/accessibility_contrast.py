"""Tier 1 Deterministic Check: W3C WCAG 2.1 AA/AAA Relative Luminance Contrast.

Evaluates:
1. CSS / inline foreground-on-background hex pairs in `TextNode`s (e.g.,
   `color: #777777; background-color: #FFFFFF`), reproducing Round 1 Plan
   Benchmark 2 (`#777777` on `#FFFFFF` = 4.48:1 FAIL vs `#767676` = 4.54:1 PASS).
2. Detected text-line bounding boxes in `ImageNode` banners via Otsu bimodal
   foreground/background pixel segmentation.
3. Computes a hue-preserving compliant `suggested_fg_hex` in CIE L*a*b* space
   by binary-searching lightness $L^*$ while holding $(a^*, b^*)$ constant.
"""

from __future__ import annotations

import re
from typing import ClassVar

from canongate.checks._vision import (
    detect_text_band_boxes,
    hex_to_rgb,
    load_rgb_image,
    rgb_to_hex,
    segment_fg_bg_rgb,
    suggest_compliant_fg_hex,
    wcag_contrast_ratio,
)
from canongate.domain.ast import ImageNode, Node, NodeKind, TextNode
from canongate.domain.canon import Canon, Rule
from canongate.domain.finding import (
    ContrastEvidence,
    Finding,
    Replace,
    Span,
    Suggestion,
    Tier,
    Trace,
)
from canongate.engine.check import Check

_CSS_FG_BG_RE = re.compile(
    r"color\s*:\s*(#[0-9A-Fa-f]{3,6})\b[^;\n]*;\s*"
    r"(?:background-color|background)\s*:\s*(#[0-9A-Fa-f]{3,6})\b",
    re.IGNORECASE,
)


class AccessibilityContrastCheck(Check):
    check_id: ClassVar[str] = "accessibility.contrast"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT, NodeKind.IMAGE})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        if isinstance(node, TextNode):
            return self._check_text_node(node)
        if isinstance(node, ImageNode):
            return self._check_image_node(node)
        return []

    def _check_text_node(self, node: TextNode) -> list[Finding]:
        findings: list[Finding] = []
        rule_ref = Rule(
            rule_id="wcag-21-aa-contrast",
            rule_type="accessibility",
            source_text="WCAG 2.1 SC 1.4.3 Contrast (Minimum): normal text requires >= 4.5:1",
        )
        for match in _CSS_FG_BG_RE.finditer(node.text):
            fg_raw, bg_raw = match.group(1), match.group(2)
            try:
                fg_rgb = hex_to_rgb(fg_raw)
                bg_rgb = hex_to_rgb(bg_raw)
            except ValueError:
                continue

            ratio = round(wcag_contrast_ratio(fg_rgb, bg_rgb), 2)
            required = 4.5
            # Exact equal colors (1.0:1) are handled by security.hidden_text
            if 1.05 <= ratio < required:
                fg_hex = rgb_to_hex(fg_rgb)
                bg_hex = rgb_to_hex(bg_rgb)
                suggested_hex = suggest_compliant_fg_hex(fg_rgb, bg_rgb, required)
                fg_span = Span(start=match.start(1), end=match.end(1))
                findings.append(
                    self.finding(
                        node=node,
                        locator=Span(start=match.start(), end=match.end()),
                        severity=65,
                        message=(
                            f"WCAG 2.1 AA contrast failure: {fg_hex} on {bg_hex} is "
                            f"{ratio:.2f}:1 (minimum {required:.1f}:1). "
                            f"Nearest compliant shade is {suggested_hex}."
                        ),
                        rule_ref=rule_ref,
                        evidence=ContrastEvidence(
                            fg_hex=fg_hex,
                            bg_hex=bg_hex,
                            contrast_ratio=ratio,
                            required_ratio=required,
                            wcag_level="AA",
                            suggested_fg_hex=suggested_hex,
                        ),
                        suggestion=Suggestion(
                            label=f"Use WCAG AA compliant {suggested_hex}",
                            replacements=(Replace(span=fg_span, replacement=suggested_hex),),
                        ),
                        trace=Trace(tier=Tier.DETERMINISTIC),
                    )
                )
        return findings

    def _check_image_node(self, node: ImageNode) -> list[Finding]:
        rgb_img = load_rgb_image(node.asset_path)
        if rgb_img is None:
            return []

        h, w, _ = rgb_img.shape
        if h < 32 or w < 32:
            return []

        rule_ref = Rule(
            rule_id="wcag-21-aa-contrast",
            rule_type="accessibility",
            source_text="WCAG 2.1 SC 1.4.3 Contrast (Minimum): normal text requires >= 4.5:1",
        )
        findings: list[Finding] = []
        for box in detect_text_band_boxes(rgb_img):
            crop = rgb_img[box.y : box.y + box.h, box.x : box.x + box.w]
            if crop.size == 0:
                continue
            fg_rgb, bg_rgb = segment_fg_bg_rgb(crop)
            ratio = round(wcag_contrast_ratio(fg_rgb, bg_rgb), 2)
            # Large text (>= 24px box height) requires 3.0:1; normal text requires 4.5:1
            required = 3.0 if box.h >= 24 else 4.5
            if 1.15 <= ratio < required:
                fg_hex = rgb_to_hex(fg_rgb)
                bg_hex = rgb_to_hex(bg_rgb)
                suggested_hex = suggest_compliant_fg_hex(fg_rgb, bg_rgb, required)
                findings.append(
                    self.finding(
                        node=node,
                        locator=box,
                        severity=65,
                        message=(
                            f"Banner text band contrast {ratio:.2f}:1 ({fg_hex} on {bg_hex}) "
                            f"is below WCAG 2.1 AA minimum {required:.1f}:1; "
                            f"use {suggested_hex}."
                        ),
                        rule_ref=rule_ref,
                        evidence=ContrastEvidence(
                            fg_hex=fg_hex,
                            bg_hex=bg_hex,
                            contrast_ratio=ratio,
                            required_ratio=required,
                            wcag_level="AA",
                            suggested_fg_hex=suggested_hex,
                        ),
                        trace=Trace(tier=Tier.DETERMINISTIC),
                    )
                )
        return findings
