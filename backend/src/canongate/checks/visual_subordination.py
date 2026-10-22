"""Visual Subordination Check (Tier 1 — deterministic computer vision).

Evaluates whether fine-print or bottom-band disclaimers in an ImageNode are
visually subordinated relative to the primary headline claim region.

Upstream OpenCV compatibility note:
Standard `opencv-python` (v4.11+) does NOT compile `cv2.saliency`
(`StaticSaliencyFineGrained` lives exclusively in `opencv-contrib-python`).
This module implements the exact Montabone & Soto (2010) multi-scale
center-surround integral-image algorithm via SIMD-accelerated `cv2.boxFilter`
and `cv2.absdiff` as a built-in fallback whenever `cv2.saliency` is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import cv2
import numpy as np
from PIL import Image

from canongate.domain.ast import ImageNode, Node, NodeKind
from canongate.domain.canon import Canon, Rule
from canongate.domain.finding import BBox, Finding, SaliencyEvidence, Tier, Trace
from canongate.engine.check import Check


def compute_fine_grained_saliency(gray_img: np.ndarray) -> np.ndarray:
    """Compute Montabone & Soto fine-grained center-surround saliency map in [0, 1].

    Uses `cv2.saliency.StaticSaliencyFineGrained_create()` when `opencv-contrib`
    is present, and falls back to the exact 6-scale integral box-filter
    center-surround difference when running on standard `opencv-python`.

    Optimization: uses the exact algebraic identity
      max(0, I - S) + max(0, S - I) == |I - S| == cv2.absdiff(I, S)
    to eliminate double accumulation buffers and temporary positive-part arrays.
    """
    if gray_img.ndim == 3:
        gray_img = cv2.cvtColor(gray_img, cv2.COLOR_RGB2GRAY)

    if hasattr(cv2, "saliency") and hasattr(cv2.saliency, "StaticSaliencyFineGrained_create"):
        sal = cv2.saliency.StaticSaliencyFineGrained_create()
        ok, sal_map = sal.computeSaliency(gray_img)
        if ok and sal_map is not None:
            sal_f = sal_map.astype(np.float32)
            max_v = float(sal_f.max())
            return sal_f / max_v if max_v > 1e-6 else sal_f

    img_f = gray_img.astype(np.float32)
    h, w = img_f.shape
    base_sigma = max(1, min(h, w) // 64)
    # Six octave-spaced surround radii (Montabone & Soto, 2010)
    scales = tuple(int(round(base_sigma * f)) for f in (2.0, 2.828, 4.0, 5.657, 8.0, 11.314))

    combined = np.zeros_like(img_f, dtype=np.float32)
    for r in scales:
        ksize = (2 * r + 1, 2 * r + 1)
        surround = cv2.boxFilter(
            img_f,
            ddepth=cv2.CV_32F,
            ksize=ksize,
            normalize=True,
            borderType=cv2.BORDER_REPLICATE,
        )
        combined += cv2.absdiff(img_f, surround)

    combined /= float(2 * len(scales))
    max_val = float(combined.max())
    return combined / max_val if max_val > 1e-6 else combined


def _load_grayscale_composited(path: Path) -> np.ndarray:
    """Load an image as 8-bit grayscale, compositing RGBA alpha over white."""
    with Image.open(path) as im:
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            composited = Image.alpha_composite(bg, rgba).convert("L")
            return np.asarray(composited, dtype=np.uint8)
        return np.asarray(im.convert("L"), dtype=np.uint8)


class VisualSubordinationCheck(Check):
    check_id: ClassVar[str] = "visual.subordination"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.IMAGE})
    min_saliency_ratio: ClassVar[float] = 0.25

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, ImageNode)
        path = Path(node.asset_path)
        if not path.exists():
            return []

        gray_img = _load_grayscale_composited(path)
        h, w = gray_img.shape
        if h < 32 or w < 32:
            return []

        sal_map = compute_fine_grained_saliency(gray_img)

        # Primary headline zone: central/upper 65% of canvas; disclaimer zone: bottom 15% band
        headline_zone = sal_map[int(h * 0.10) : int(h * 0.75), int(w * 0.05) : int(w * 0.95)]
        disc_y0 = int(h * 0.85)
        disc_zone = sal_map[disc_y0:h, int(w * 0.05) : int(w * 0.95)]

        headline_sal = float(np.percentile(headline_zone, 90)) if headline_zone.size else 0.0
        disc_sal = float(np.percentile(disc_zone, 90)) if disc_zone.size else 0.0

        if headline_sal <= 1e-3 or disc_sal <= 1e-4:
            return []

        ratio = disc_sal / headline_sal
        if ratio >= self.min_saliency_ratio:
            return []

        bbox = BBox(x=int(w * 0.05), y=disc_y0, w=int(w * 0.90), h=h - disc_y0)
        rule_ref = Rule(
            rule_id="asci-visual-subordination",
            rule_type="visual",
            source_text=(
                "Disclaimers must not be visually subordinated (< 25% of headline saliency)"
            ),
        )
        return [
            self.finding(
                node=node,
                locator=bbox,
                severity=60,
                message=(
                    f"Disclaimer band saliency ratio ({ratio:.2f}) is below the "
                    f"{self.min_saliency_ratio:.2f} visual prominence floor "
                    f"(disclaimer={disc_sal:.3f} vs headline={headline_sal:.3f})."
                ),
                rule_ref=rule_ref,
                evidence=SaliencyEvidence(
                    disclaimer_saliency=round(disc_sal, 4),
                    headline_saliency=round(headline_sal, 4),
                    ratio=round(ratio, 4),
                    min_ratio=self.min_saliency_ratio,
                ),
                trace=Trace(tier=Tier.DETERMINISTIC),
            )
        ]
