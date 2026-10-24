"""Tier 1 Check: ASCI 26px Disclaimer Height, OCR Confidence Gate & CCPA Script Parity.

Enforces three multimodal regulatory requirements (Round 1 Plan §3.1, §3.4 & Named Improvement #3):
1. **ASCI Digital Media Disclaimer Guidelines:** Disclaimers in the bottom
   banner zone ($y \\ge 0.78 H$) must scale proportionally with image height
   ($\\ge 26\\text{px}$ at $1080\\text{p}$, i.e., $\\ge 2.4\\%$ of $H$, with an
   absolute legible floor of $12\\text{px}$ on standard web banners).
2. **PaddleOCR Fine-Print Confidence & 10px Height Gate (Plan §3.1 p. 4):**
   Any banner OCR text box tagged onto `{path}/ocr_low_conf[{i}][conf=...,bbox=...,img_h=...]`
   with OCR confidence $< 0.75$ or pixel height $< 10\\text{px}$ is flagged for
   human review.
3. **CCPA 2022 Misleading Advertisement Guidelines (Clause 11):** Disclaimers
   must be in the same language/script as the primary claim. Flags a Blocker
   (`script_mismatch=True`, `severity=75`) both when a Devanagari (Hindi) headline
   and a Latin-only (English) disclaimer appear inside a single `TextNode` AND
   when they appear across separate `TextNode`s / pages / banner OCR nodes via
   `run_bundle(ast, canon)`.
"""

from __future__ import annotations

import re
from typing import ClassVar

from canongate.checks._vision import detect_text_band_boxes, load_rgb_image
from canongate.domain.ast import ContentAST, ImageNode, Node, NodeKind, TextNode
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
    r"\b(?:Disclaimer|Note|T&C\s+Apply)\s*:|अस्वीकरण\s*:?|शर्तें\s+लागू|नियम\s+(?:एवं|और)\s+शर्तें)",
    re.IGNORECASE,
)
_LOW_CONF_PATH_RE = re.compile(
    r"/ocr_low_conf\[\d+\]\[conf=([0-9.]+),bbox=(\d+)_(\d+)_(\d+)_(\d+),img_h=(\d+)\]"
)


def _has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text))


def _has_latin(text: str) -> bool:
    return bool(_LATIN_WORD_RE.search(text))


class LegibilityPlacementCheck(Check):
    check_id: ClassVar[str] = "legibility.placement"
    check_version: ClassVar[str] = "1.2"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.IMAGE, NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        if isinstance(node, TextNode):
            findings = self._check_ocr_confidence_gate(node)
            findings.extend(self._check_script_parity(node))
            return findings
        if isinstance(node, ImageNode):
            return self._check_banner_legibility(node)
        return []

    def _check_ocr_confidence_gate(self, node: TextNode) -> list[Finding]:
        m = _LOW_CONF_PATH_RE.search(node.path)
        if m is None:
            return []

        conf = float(m.group(1))
        bh = float(m.group(5))
        img_h = int(m.group(6))
        req_px = round(max(10.0, 26.0 * (img_h / 1080.0)), 1) if img_h > 0 else 10.0
        est_x = round(bh * 0.52, 2)

        rule_ref = Rule(
            rule_id="ocr-fine-print-confidence-gate",
            rule_type="legibility",
            source_text=(
                "CanonGate OCR Gate: banner fine-print boxes with OCR confidence < 0.75 "
                "or height < 10px require human review."
            ),
        )
        reason_parts: list[str] = []
        if conf < 0.75:
            reason_parts.append(f"OCR confidence {conf:.2f} < 0.75")
        if bh < 10.0:
            reason_parts.append(f"box height {bh:.0f}px < 10px floor")
        reason_str = " and ".join(reason_parts) or f"OCR confidence {conf:.2f}"

        return [
            self.finding(
                node=node,
                locator=Span(start=0, end=len(node.text)),
                severity=65 if bh < 10.0 else 45,
                message=(
                    f"Banner fine-print legibility warning ({reason_str}): "
                    f"recognized text {node.text[:60]!r} requires human review."
                ),
                rule_ref=rule_ref,
                evidence=LegibilityEvidence(
                    measured_box_px=bh,
                    estimated_x_height_px=est_x,
                    required_px=req_px,
                    image_height_px=img_h,
                    ocr_confidence=conf,
                    script_mismatch=False,
                ),
                trace=Trace(tier=Tier.DETERMINISTIC, model_sha="pp-ocrv5-confidence-gate"),
            )
        ]

    def run_bundle(self, ast: ContentAST, canon: Canon) -> list[Finding]:
        """Cross-node / multi-page brochure script parity check under CCPA 2022 Clause 11."""
        text_nodes = ast.text_nodes()
        if len(text_nodes) < 2:
            return []

        claim_nodes = [tn for tn in text_nodes if not _DISCLAIMER_SPLIT_RE.search(tn.text)]
        disc_nodes = [
            tn
            for tn in text_nodes
            if (m := _DISCLAIMER_SPLIT_RE.search(tn.text)) is not None and m.start() < 15
        ]
        if not claim_nodes or not disc_nodes:
            return []

        any_hi_claim = any(_has_devanagari(tn.text) for tn in claim_nodes)
        any_lat_claim = any(
            _has_latin(tn.text) and not _has_devanagari(tn.text) for tn in claim_nodes
        )
        findings: list[Finding] = []
        rule_ref = Rule(
            rule_id="ccpa-2022-clause-11-script-parity",
            rule_type="legibility",
            source_text=(
                "CCPA 2022 Clause 11: A disclaimer shall be in the same language/script "
                "as the primary claim of the advertisement."
            ),
        )
        for dn in disc_nodes:
            disc_hi = _has_devanagari(dn.text)
            disc_lat = _has_latin(dn.text)
            if (any_hi_claim and not disc_hi and disc_lat) or (
                any_lat_claim and disc_hi and not disc_lat
            ):
                findings.append(
                    self.finding(
                        node=dn,
                        locator=Span(start=0, end=len(dn.text)),
                        severity=75,
                        message=(
                            "CCPA 2022 Clause 11 cross-node script mismatch: primary campaign "
                            "claim and disclaimer node use different scripts (Devanagari vs Latin)."
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
                )
        return findings

    def _check_script_parity(self, node: TextNode) -> list[Finding]:
        match = _DISCLAIMER_SPLIT_RE.search(node.text)
        if match is None:
            return []

        claim_part = node.text[: match.start()]
        disclaimer_part = node.text[match.start() :]

        claim_hi = _has_devanagari(claim_part)
        disc_hi = _has_devanagari(disclaimer_part)
        disc_lat = _has_latin(disclaimer_part)

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
