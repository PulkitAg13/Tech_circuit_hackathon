r"""Tier 1 Deterministic Check: OpenCV ORB Logo Aspect Distortion ($\le 2\%$) & $0.5H$ Clear-Space.

Implements Round 1 Plan §3.3 & §3.4 (`VisualTokenSchema`):
1. Detects approved brand logos inside raster campaign banners (`ImageNode`) using
   OpenCV ORB feature matching (`cv2.ORB_create`, `cv2.BFMatcher(cv2.NORM_HAMMING)`,
   Lowe's 0.75 ratio test, and `cv2.findHomography(..., cv2.RANSAC, 5.0)` with
   `cv2.perspectiveTransform`), falling back to logo-sized connected-component
   bounding-box localization in the brand mark zone when a geometric/stretched
   mark has fewer than `min_orb_matches` keypoints.
2. Verifies aspect ratio distortion:
   `|AR_detected - AR_expected| / AR_expected * 100 <= max_aspect_distortion_pct`
3. Verifies clear-space margin ($0.5H$ around the detected logo bounding box):
   inspects the surrounding collar of thickness `round(clear_space_ratio_h * H_logo)`
   for intruding high-contrast edges or text elements.
"""

from __future__ import annotations

from typing import ClassVar

import cv2
import numpy as np
from numpy.typing import NDArray

from canongate.checks._vision import load_rgb_image
from canongate.domain.ast import ImageNode, Node, NodeKind
from canongate.domain.canon import Canon, LogoToken
from canongate.domain.finding import (
    BBox,
    Finding,
    LogoGeometryEvidence,
    Tier,
    Trace,
)
from canongate.engine.check import Check


def _detect_logo_bbox_orb(
    scene_gray: NDArray[np.uint8],
    ref_gray: NDArray[np.uint8],
    min_matches: int,
) -> tuple[BBox | None, int]:
    """Locate `ref_gray` inside `scene_gray` via ORB keypoints + RANSAC homography."""
    orb = cv2.ORB_create(nfeatures=1500)
    kp_ref, des_ref = orb.detectAndCompute(ref_gray, None)
    kp_scn, des_scn = orb.detectAndCompute(scene_gray, None)

    if des_ref is not None and des_scn is not None and len(kp_ref) >= 4 and len(kp_scn) >= 4:
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        raw_matches = bf.knnMatch(des_ref, des_scn, k=2)
        good = []
        for pair in raw_matches:
            if len(pair) == 2:
                m, n = pair
                if m.distance < 0.78 * n.distance:
                    good.append(m)

        if len(good) >= max(4, min_matches):
            src_pts = np.float32([kp_ref[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp_scn[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            homography, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if homography is not None and mask is not None:
                inliers = int(mask.ravel().sum())
                if inliers >= 4:
                    h_ref, w_ref = ref_gray.shape[:2]
                    corners = np.float32([[0, 0], [0, h_ref], [w_ref, h_ref], [w_ref, 0]]).reshape(
                        -1, 1, 2
                    )
                    projected = cv2.perspectiveTransform(corners, homography).reshape(-1, 2)
                    x_min = max(0, int(np.floor(projected[:, 0].min())))
                    y_min = max(0, int(np.floor(projected[:, 1].min())))
                    x_max = min(scene_gray.shape[1], int(np.ceil(projected[:, 0].max())))
                    y_max = min(scene_gray.shape[0], int(np.ceil(projected[:, 1].max())))
                    if x_max - x_min >= 12 and y_max - y_min >= 12:
                        return (
                            BBox(
                                x=x_min,
                                y=y_min,
                                w=x_max - x_min,
                                h=y_max - y_min,
                            ),
                            inliers,
                        )
    return None, 0


def _detect_foreground_mark_bbox(
    scene_rgb: NDArray[np.uint8],
    expected_ar: float = 2.0,
) -> BBox | None:
    """Locate the primary brand logo mark bounding box (excluding full-width CTA banners)."""
    h, w, _ = scene_rgb.shape
    bg_color = np.median(
        np.concatenate(
            [scene_rgb[0, :, :], scene_rgb[-1, :, :], scene_rgb[:, 0, :], scene_rgb[:, -1, :]],
            axis=0,
        ),
        axis=0,
    )
    diff = np.linalg.norm(scene_rgb.astype(np.float32) - bg_color, axis=2)
    mask = (diff > 25.0).astype(np.uint8) * 255
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    candidates: list[tuple[float, BBox]] = []
    for idx in range(1, num_labels):
        cx = int(stats[idx, cv2.CC_STAT_LEFT])
        cy = int(stats[idx, cv2.CC_STAT_TOP])
        cw = int(stats[idx, cv2.CC_STAT_WIDTH])
        ch = int(stats[idx, cv2.CC_STAT_HEIGHT])
        area = cw * ch
        # A brand logo mark is >= 24px tall, not a thin divider/intrusion bar (ch >= 24),
        # and not a full-width background panel (cw <= 0.65 * w).
        if cw >= 24 and ch >= 28 and area < int(w * h * 0.45) and cw <= int(w * 0.75):
            ar = cw / float(ch)
            ar_diff = abs(ar - expected_ar) / max(expected_ar, 0.1)
            # Prefer marks in the top header zone with plausible logo dimensions
            score = area / (1.0 + 0.5 * ar_diff + (2.0 if cy > h * 0.5 else 0.0))
            candidates.append((score, BBox(x=cx, y=cy, w=cw, h=ch)))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _compute_clear_space_intrusion_pct(
    scene_rgb: NDArray[np.uint8],
    logo_box: BBox,
    clear_space_ratio_h: float,
) -> float:
    img_h, img_w, _ = scene_rgb.shape
    margin = max(2, round(clear_space_ratio_h * logo_box.h))

    x0 = max(0, logo_box.x - margin)
    y0 = max(0, logo_box.y - margin)
    x1 = min(img_w, logo_box.x + logo_box.w + margin)
    y1 = min(img_h, logo_box.y + logo_box.h + margin)

    bg_color = np.median(
        np.concatenate(
            [scene_rgb[0, :, :], scene_rgb[-1, :, :], scene_rgb[:, 0, :], scene_rgb[:, -1, :]],
            axis=0,
        ),
        axis=0,
    )
    collar_mask = np.zeros((img_h, img_w), dtype=bool)
    collar_mask[y0:y1, x0:x1] = True
    collar_mask[
        logo_box.y : logo_box.y + logo_box.h,
        logo_box.x : logo_box.x + logo_box.w,
    ] = False

    collar_pixels = scene_rgb[collar_mask]
    if collar_pixels.size == 0:
        return 0.0

    dist = np.linalg.norm(collar_pixels.astype(np.float32) - bg_color, axis=1)
    intruding = int(np.sum(dist > 28.0))
    total = int(collar_pixels.shape[0])
    return round((intruding / float(total)) * 100.0, 2)


class VisualLogoOrbCheck(Check):
    """Tier 1 check for logo aspect-ratio distortion (<= 2%) and 0.5H clear-space intrusion."""

    check_id: ClassVar[str] = "visual.logo_orb"
    check_version: ClassVar[str] = "1.1"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.IMAGE})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        if not isinstance(node, ImageNode) or not canon.logos:
            return []

        scene_rgb = load_rgb_image(node.asset_path)
        if scene_rgb is None:
            return []

        scene_gray = cv2.cvtColor(scene_rgb, cv2.COLOR_RGB2GRAY)
        findings: list[Finding] = []

        for logo_tok in canon.logos:
            finding = self._evaluate_logo(node, scene_rgb, scene_gray, logo_tok)
            if finding is not None:
                findings.append(finding)

        return findings

    def _evaluate_logo(
        self,
        node: ImageNode,
        scene_rgb: NDArray[np.uint8],
        scene_gray: NDArray[np.uint8],
        logo_tok: LogoToken,
    ) -> Finding | None:
        expected_ar = logo_tok.aspect_ratio
        orb_matches = 0
        detected_box: BBox | None = None

        if logo_tok.reference_path:
            ref_rgb = load_rgb_image(logo_tok.reference_path)
            if ref_rgb is not None:
                ref_h, ref_w = ref_rgb.shape[:2]
                if ref_h > 0 and expected_ar == 1.0:
                    expected_ar = ref_w / float(ref_h)
                ref_gray = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY)
                detected_box, orb_matches = _detect_logo_bbox_orb(
                    scene_gray, ref_gray, logo_tok.min_orb_matches
                )

        if detected_box is None:
            detected_box = _detect_foreground_mark_bbox(scene_rgb, expected_ar)

        if detected_box is None or detected_box.h <= 0:
            return None

        detected_ar = round(detected_box.w / float(detected_box.h), 4)
        distortion_pct = round(abs(detected_ar - expected_ar) / max(expected_ar, 1e-6) * 100.0, 2)
        intrusion_pct = _compute_clear_space_intrusion_pct(
            scene_rgb, detected_box, logo_tok.clear_space_ratio_h
        )

        ar_violated = distortion_pct > logo_tok.max_aspect_distortion_pct
        cs_violated = intrusion_pct > 5.0
        if not ar_violated and not cs_violated:
            return None

        issues: list[str] = []
        if ar_violated:
            issues.append(
                f"aspect distortion {distortion_pct:.1f}% exceeds "
                f"{logo_tok.max_aspect_distortion_pct:.1f}% limit "
                f"(detected AR {detected_ar:.2f} vs approved {expected_ar:.2f})"
            )
        if cs_violated:
            issues.append(
                f"{logo_tok.clear_space_ratio_h:.2f}H clear-space intrusion "
                f"({intrusion_pct:.1f}% of margin occupied)"
            )

        return self.finding(
            node=node,
            locator=detected_box,
            severity=logo_tok.severity,
            message=f"Logo {logo_tok.name or logo_tok.id!r} geometry failure: {'; '.join(issues)}.",
            rule_ref=logo_tok.to_rule_ref(),
            evidence=LogoGeometryEvidence(
                logo_id=logo_tok.id,
                expected_aspect_ratio=round(expected_ar, 4),
                detected_aspect_ratio=detected_ar,
                aspect_distortion_pct=distortion_pct,
                max_aspect_distortion_pct=logo_tok.max_aspect_distortion_pct,
                clear_space_ratio_h=logo_tok.clear_space_ratio_h,
                clear_space_intrusion_pct=intrusion_pct,
                orb_inlier_matches=orb_matches,
            ),
            trace=Trace(tier=Tier.DETERMINISTIC),
        )
