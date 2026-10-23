"""Tier 1 Deterministic Check: Perceptual Brand Palette Drift via CIEDE2000.

Segments flat colour swatches/regions on `ImageNode` assets (or explicit hex
swatches in `TextNode` style declarations) and computes the exact Sharma, Wu, &
Dalal (2005) CIEDE2000 perceptual colour distance $\\Delta E_{00}$ against
`Canon.palette` (`ColorToken.max_delta_e`).
"""

from __future__ import annotations

import re
from typing import ClassVar

import cv2
import numpy as np

from canongate.checks._vision import (
    delta_e_ciede2000,
    hex_to_rgb,
    load_rgb_image,
    rgb_to_hex,
    rgb_to_lab,
)
from canongate.domain.ast import ImageNode, Node, NodeKind, TextNode
from canongate.domain.canon import Canon, ColorToken
from canongate.domain.finding import (
    BBox,
    ColorDistance,
    Finding,
    Replace,
    Span,
    Suggestion,
    Tier,
    Trace,
)
from canongate.engine.check import Check

_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
# Upper bound distinguishing an off-shade drift of a brand colour from a neutral/unrelated colour
_MAX_DRIFT_HORIZON = 24.0


def _nearest_palette_token(
    rgb: tuple[int, int, int],
    palette: tuple[ColorToken, ...],
) -> tuple[ColorToken, float]:
    lab = rgb_to_lab(rgb)
    best_tok = palette[0]
    best_de = float("inf")
    for tok in palette:
        de = delta_e_ciede2000(lab, rgb_to_lab(tok.rgb))
        if de < best_de:
            best_de = de
            best_tok = tok
    return best_tok, round(best_de, 2)


class VisualPaletteDriftCheck(Check):
    check_id: ClassVar[str] = "visual.palette_drift"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.IMAGE, NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        palette = canon.color_tokens()
        if not palette:
            return []

        if isinstance(node, TextNode):
            return self._check_text_swatches(node, canon, palette)
        if isinstance(node, ImageNode):
            return self._check_image_regions(node, canon, palette)
        return []

    def _check_text_swatches(
        self,
        node: TextNode,
        canon: Canon,
        palette: tuple[ColorToken, ...],
    ) -> list[Finding]:
        findings: list[Finding] = []
        for match in _HEX_RE.finditer(node.text):
            found_hex = match.group(0).upper()
            rgb = hex_to_rgb(found_hex)
            # Ignore pure white/black neutral backgrounds unless explicitly in palette
            if found_hex in ("#FFFFFF", "#000000") and all(
                t.hex.upper() != found_hex for t in palette
            ):
                continue

            nearest_tok, delta_e = _nearest_palette_token(rgb, palette)
            if nearest_tok.max_delta_e < delta_e <= _MAX_DRIFT_HORIZON:
                span = Span(start=match.start(), end=match.end())
                approved_hex = nearest_tok.hex.upper()
                findings.append(
                    self.finding(
                        node=node,
                        locator=span,
                        severity=45,
                        message=(
                            f"Colour {found_hex} drifts from approved brand swatch "
                            f"{nearest_tok} by ΔE00 = {delta_e:.2f} "
                            f"(max allowed {nearest_tok.max_delta_e:.1f})."
                        ),
                        rule_ref=canon.to_rule_ref(nearest_tok),
                        evidence=ColorDistance(
                            found_hex=found_hex,
                            approved_hex=approved_hex,
                            delta_e=delta_e,
                            max_allowed=nearest_tok.max_delta_e,
                        ),
                        suggestion=Suggestion(
                            label=f"Snap colour to {approved_hex} ({nearest_tok.name})",
                            replacements=(Replace(span=span, replacement=approved_hex),),
                        ),
                        trace=Trace(tier=Tier.DETERMINISTIC),
                    )
                )
        return findings

    def _check_image_regions(
        self,
        node: ImageNode,
        canon: Canon,
        palette: tuple[ColorToken, ...],
    ) -> list[Finding]:
        rgb_img = load_rgb_image(node.asset_path)
        if rgb_img is None:
            return []

        h, w, _ = rgb_img.shape
        if h < 16 or w < 16:
            return []

        # Quantize colours to 4-bit per channel (16x16x16 bins) to locate dominant flat regions
        quant = (rgb_img // 16) * 16 + 8
        flat_keys = (
            quant[:, :, 0].astype(np.int32) * 65536
            + quant[:, :, 1].astype(np.int32) * 256
            + quant[:, :, 2].astype(np.int32)
        )
        unique_keys, counts = np.unique(flat_keys, return_counts=True)
        total_px = h * w
        order = np.argsort(-counts)

        findings: list[Finding] = []
        seen_tokens: set[str] = set()

        for idx in order[:6]:
            if int(counts[idx]) < max(32, int(total_px * 0.04)):
                break
            key_val = int(unique_keys[idx])
            mask = flat_keys == key_val
            med_vals = np.median(rgb_img[mask], axis=0)
            rgb = (
                int(round(float(med_vals[0]))),
                int(round(float(med_vals[1]))),
                int(round(float(med_vals[2]))),
            )
            # Skip near-achromatic grey/white/black backgrounds (low saturation)
            if max(rgb) - min(rgb) < 18:
                continue

            nearest_tok, delta_e = _nearest_palette_token(rgb, palette)
            if (
                nearest_tok.id not in seen_tokens
                and nearest_tok.max_delta_e < delta_e <= _MAX_DRIFT_HORIZON
            ):
                seen_tokens.add(nearest_tok.id)
                mask_u8 = mask.astype(np.uint8) * 255
                bx, by, bw, bh = cv2.boundingRect(mask_u8)
                found_hex = rgb_to_hex(rgb)
                approved_hex = nearest_tok.hex.upper()
                findings.append(
                    self.finding(
                        node=node,
                        locator=BBox(x=int(bx), y=int(by), w=int(bw), h=int(bh)),
                        severity=45,
                        message=(
                            f"Banner region colour {found_hex} drifts from approved swatch "
                            f"{nearest_tok} by ΔE00 = {delta_e:.2f} "
                            f"(max allowed {nearest_tok.max_delta_e:.1f})."
                        ),
                        rule_ref=canon.to_rule_ref(nearest_tok),
                        evidence=ColorDistance(
                            found_hex=found_hex,
                            approved_hex=approved_hex,
                            delta_e=delta_e,
                            max_allowed=nearest_tok.max_delta_e,
                        ),
                        trace=Trace(tier=Tier.DETERMINISTIC),
                    )
                )
        return findings
