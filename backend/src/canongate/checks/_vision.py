r"""Shared deterministic vision, colourimetric (CIE Lab / CIEDE2000), WCAG 2.1,
and DesignAlternativeProvider visual repair synthesis.

Why this module lives inside `canongate.checks`:
1. `import-linter` forbids `canongate.checks` from importing `canongate.parsers`.
2. Provides exact W3C WCAG 2.1 relative luminance, CIE L*a*b* (D65) conversion,
   vectorized Sharma, Wu, & Dalal (2005) CIEDE2000 (`delta_e_ciede2000`), and
   `DesignAlternativeProvider` multi-candidate visual repair synthesis.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable

import cv2
import numpy as np
from PIL import Image

from canongate.domain.finding import BBox


@lru_cache(maxsize=32)
def _load_rgb_image_cached(resolved_path: str, mtime_ns: int, size: int) -> np.ndarray | None:
    try:
        with Image.open(resolved_path) as im:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                rgb = Image.alpha_composite(bg, rgba).convert("RGB")
            else:
                rgb = im.convert("RGB")
            arr = np.asarray(rgb, dtype=np.uint8)
            arr.setflags(write=False)
            return arr
    except Exception:
        return None


def load_rgb_image(path: str | Path) -> np.ndarray | None:
    """Load an image file as a cached `(H, W, 3)` uint8 RGB array, compositing alpha over white."""
    if not path:
        return None
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return None
    return _load_rgb_image_cached(str(p.resolve()), st.st_mtime_ns, st.st_size)


@lru_cache(maxsize=512)
def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Parse `#RRGGBB` or `#RGB` into `(R, G, B)` in `0..255`."""
    h = hex_str.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        raise ValueError(f"Invalid hex colour: {hex_str!r}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


@lru_cache(maxsize=512)
def relative_luminance(rgb: tuple[int, int, int]) -> float:
    r"""W3C WCAG 2.1 relative luminance $L \in [0, 1]$ from 8-bit sRGB."""
    lin: list[float] = []
    for channel in rgb:
        c = channel / 255.0
        lin.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def wcag_contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    r"""W3C WCAG 2.1 contrast ratio $(L_1 + 0.05) / (L_2 + 0.05) \in [1.0, 21.0]$."""
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


@lru_cache(maxsize=512)
def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Convert 8-bit sRGB `(R, G, B)` to CIE L*a*b* (D65 reference white)."""
    lin = [
        (c / 255.0) / 12.92 if (c / 255.0) <= 0.04045 else (((c / 255.0) + 0.055) / 1.055) ** 2.4
        for c in rgb
    ]
    x = (0.4124564 * lin[0] + 0.3575761 * lin[1] + 0.1804375 * lin[2]) / 0.95047
    y = (0.2126729 * lin[0] + 0.7151522 * lin[1] + 0.0721750 * lin[2]) / 1.00000
    z = (0.0193339 * lin[0] + 0.1191920 * lin[1] + 0.9503041 * lin[2]) / 1.08883

    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    fx = x ** (1.0 / 3.0) if x > eps else (kappa * x + 16.0) / 116.0
    fy = y ** (1.0 / 3.0) if y > eps else (kappa * y + 16.0) / 116.0
    fz = z ** (1.0 / 3.0) if z > eps else (kappa * z + 16.0) / 116.0
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def lab_to_rgb(lab: tuple[float, float, float]) -> tuple[int, int, int]:
    """Convert CIE L*a*b* (D65) back to 8-bit sRGB `(R, G, B)`."""
    l_star, a_star, b_star = lab
    fy = (l_star + 16.0) / 116.0
    fx = a_star / 500.0 + fy
    fz = fy - b_star / 200.0

    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    xr = fx**3 if fx**3 > eps else (116.0 * fx - 16.0) / kappa
    yr = ((l_star + 16.0) / 116.0) ** 3 if l_star > kappa * eps else l_star / kappa
    zr = fz**3 if fz**3 > eps else (116.0 * fz - 16.0) / kappa

    x = xr * 0.95047
    y = yr * 1.00000
    z = zr * 1.08883

    r_lin = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g_lin = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    b_lin = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z

    out: list[int] = []
    for c_lin in (r_lin, g_lin, b_lin):
        c_clamped = max(0.0, min(1.0, c_lin))
        srgb = (
            12.92 * c_clamped
            if c_clamped <= 0.0031308
            else 1.055 * (c_clamped ** (1.0 / 2.4)) - 0.055
        )
        out.append(max(0, min(255, round(srgb * 255.0))))
    return (out[0], out[1], out[2])


def suggest_compliant_fg_hex(
    fg_rgb: tuple[int, int, int],
    bg_rgb: tuple[int, int, int],
    required_ratio: float = 4.5,
) -> str:
    """Find the nearest hue-preserving foreground hex in CIE Lab that meets `required_ratio`."""
    if wcag_contrast_ratio(fg_rgb, bg_rgb) >= required_ratio:
        return rgb_to_hex(fg_rgb)

    _, a_star, b_star = rgb_to_lab(fg_rgb)
    bg_lum = relative_luminance(bg_rgb)
    darken = bg_lum >= 0.18

    lo, hi = (0.0, 100.0)
    best_rgb = (0, 0, 0) if darken else (255, 255, 255)
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        cand_rgb = lab_to_rgb((mid, a_star, b_star))
        ratio = wcag_contrast_ratio(cand_rgb, bg_rgb)
        if ratio >= required_ratio:
            best_rgb = cand_rgb
            if darken:
                lo = mid
            else:
                hi = mid
        else:
            if darken:
                hi = mid
            else:
                lo = mid
    return rgb_to_hex(best_rgb)


def delta_e_ciede2000(
    lab1: tuple[float, float, float],
    lab2: tuple[float, float, float],
) -> float:
    r"""Exact Sharma, Wu, & Dalal (2005) CIEDE2000 perceptual colour distance $\Delta E_{00}$."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2

    c1 = float(np.hypot(a1, b1))
    c2 = float(np.hypot(a2, b2))
    c_bar = 0.5 * (c1 + c2)
    c_bar7 = c_bar**7
    g = 0.5 * (1.0 - float(np.sqrt(c_bar7 / (c_bar7 + 25.0**7))))

    a1_p = (1.0 + g) * a1
    a2_p = (1.0 + g) * a2
    c1_p = float(np.hypot(a1_p, b1))
    c2_p = float(np.hypot(a2_p, b2))

    h1_p = 0.0 if c1_p == 0.0 else float(np.degrees(np.arctan2(b1, a1_p)) % 360.0)
    h2_p = 0.0 if c2_p == 0.0 else float(np.degrees(np.arctan2(b2, a2_p)) % 360.0)

    delta_l_p = l2 - l1
    delta_c_p = c2_p - c1_p

    if c1_p * c2_p == 0.0:
        delta_h_p = 0.0
    elif abs(h2_p - h1_p) <= 180.0:
        delta_h_p = h2_p - h1_p
    elif h2_p - h1_p > 180.0:
        delta_h_p = (h2_p - h1_p) - 360.0
    else:
        delta_h_p = (h2_p - h1_p) + 360.0

    delta_big_h_p = 2.0 * float(np.sqrt(c1_p * c2_p)) * float(np.sin(np.radians(delta_h_p / 2.0)))

    l_bar_p = 0.5 * (l1 + l2)
    c_bar_p = 0.5 * (c1_p + c2_p)

    if c1_p * c2_p == 0.0:
        h_bar_p = h1_p + h2_p
    elif abs(h1_p - h2_p) <= 180.0:
        h_bar_p = 0.5 * (h1_p + h2_p)
    elif h1_p + h2_p < 360.0:
        h_bar_p = 0.5 * (h1_p + h2_p + 360.0)
    else:
        h_bar_p = 0.5 * (h1_p + h2_p - 360.0)

    t = (
        1.0
        - 0.17 * float(np.cos(np.radians(h_bar_p - 30.0)))
        + 0.24 * float(np.cos(np.radians(2.0 * h_bar_p)))
        + 0.32 * float(np.cos(np.radians(3.0 * h_bar_p + 6.0)))
        - 0.20 * float(np.cos(np.radians(4.0 * h_bar_p - 63.0)))
    )

    delta_theta = 30.0 * float(np.exp(-(((h_bar_p - 275.0) / 25.0) ** 2)))
    c_bar_p7 = c_bar_p**7
    r_c = 2.0 * float(np.sqrt(c_bar_p7 / (c_bar_p7 + 25.0**7)))
    l_term = (l_bar_p - 50.0) ** 2
    s_l = 1.0 + (0.015 * l_term) / float(np.sqrt(20.0 + l_term))
    s_c = 1.0 + 0.045 * c_bar_p
    s_h = 1.0 + 0.015 * c_bar_p * t
    r_t = -float(np.sin(np.radians(2.0 * delta_theta))) * r_c

    term_l = delta_l_p / s_l
    term_c = delta_c_p / s_c
    term_h = delta_big_h_p / s_h
    return float(np.sqrt(term_l**2 + term_c**2 + term_h**2 + r_t * term_c * term_h))


@dataclass(frozen=True, slots=True)
class VisualAlternativeCandidate:
    """A re-verified visual repair candidate for a failing banner or contrast region."""

    candidate_id: str
    label: str
    foreground_hex: str
    background_hex: str
    contrast_ratio: float
    delta_e_from_brand: float
    reverified: bool


@runtime_checkable
class DesignAlternativeProvider(Protocol):
    """Pluggable provider hook (`DesignAlternativeProvider`) for generating visual repairs."""

    def suggest_alternatives(
        self,
        fg_rgb: tuple[int, int, int],
        bg_rgb: tuple[int, int, int],
        *,
        brand_palette_hexes: Sequence[str] = (),
        required_ratio: float = 4.5,
        max_candidates: int = 3,
    ) -> list[VisualAlternativeCandidate]:
        """Return up to `max_candidates` re-verified visual repair alternatives."""


class CielabDesignAlternativeProvider:
    """Default deterministic CIELAB + WCAG 2.1 `DesignAlternativeProvider` implementation.

    Synthesizes up to 3 distinct, re-verified compliant visual alternatives:
    1. Minimal `L*` lightness shift preserving original hue/chroma (`WCAG AA >= 4.5:1`).
    2. High-contrast `WCAG AAA >= 7.0:1` editorial variant for fine-print legibility.
    3. Nearest Canon brand palette token snap (minimizing $\\Delta E_{00}$ while meeting contrast).
    """

    def suggest_alternatives(
        self,
        fg_rgb: tuple[int, int, int],
        bg_rgb: tuple[int, int, int],
        *,
        brand_palette_hexes: Sequence[str] = (),
        required_ratio: float = 4.5,
        max_candidates: int = 3,
    ) -> list[VisualAlternativeCandidate]:
        bg_hex = rgb_to_hex(bg_rgb)
        fg_lab = rgb_to_lab(fg_rgb)
        candidates: list[VisualAlternativeCandidate] = []

        # Candidate 1: Hue-preserving WCAG AA lightness shift
        aa_hex = suggest_compliant_fg_hex(fg_rgb, bg_rgb, required_ratio=required_ratio)
        aa_rgb = hex_to_rgb(aa_hex)
        aa_ratio = round(wcag_contrast_ratio(aa_rgb, bg_rgb), 2)
        aa_de = round(delta_e_ciede2000(fg_lab, rgb_to_lab(aa_rgb)), 2)
        candidates.append(
            VisualAlternativeCandidate(
                candidate_id="alt-1-wcag-aa",
                label=f"Hue-Preserving WCAG AA ({aa_hex} on {bg_hex}, {aa_ratio}:1)",
                foreground_hex=aa_hex,
                background_hex=bg_hex,
                contrast_ratio=aa_ratio,
                delta_e_from_brand=aa_de,
                reverified=aa_ratio >= required_ratio,
            )
        )

        # Candidate 2: High-legibility WCAG AAA (>= 7.0:1) variant
        aaa_target = max(7.0, required_ratio + 1.5)
        aaa_hex = suggest_compliant_fg_hex(fg_rgb, bg_rgb, required_ratio=aaa_target)
        if aaa_hex != aa_hex:
            aaa_rgb = hex_to_rgb(aaa_hex)
            aaa_ratio = round(wcag_contrast_ratio(aaa_rgb, bg_rgb), 2)
            aaa_de = round(delta_e_ciede2000(fg_lab, rgb_to_lab(aaa_rgb)), 2)
            candidates.append(
                VisualAlternativeCandidate(
                    candidate_id="alt-2-wcag-aaa",
                    label=f"High-Contrast WCAG AAA ({aaa_hex} on {bg_hex}, {aaa_ratio}:1)",
                    foreground_hex=aaa_hex,
                    background_hex=bg_hex,
                    contrast_ratio=aaa_ratio,
                    delta_e_from_brand=aaa_de,
                    reverified=aaa_ratio >= required_ratio,
                )
            )

        # Candidate 3: Nearest Canon Brand Palette Token adjusted for contrast
        if brand_palette_hexes:
            best_brand: VisualAlternativeCandidate | None = None
            for b_hex in brand_palette_hexes:
                try:
                    b_rgb = hex_to_rgb(b_hex)
                except ValueError:
                    continue
                adj_hex = suggest_compliant_fg_hex(b_rgb, bg_rgb, required_ratio=required_ratio)
                adj_rgb = hex_to_rgb(adj_hex)
                adj_ratio = round(wcag_contrast_ratio(adj_rgb, bg_rgb), 2)
                de = round(delta_e_ciede2000(rgb_to_lab(b_rgb), rgb_to_lab(adj_rgb)), 2)
                cand = VisualAlternativeCandidate(
                    candidate_id="alt-3-brand-palette",
                    label=f"Brand Palette Snap ({adj_hex} on {bg_hex}, {adj_ratio}:1, ΔE₀₀={de})",
                    foreground_hex=adj_hex,
                    background_hex=bg_hex,
                    contrast_ratio=adj_ratio,
                    delta_e_from_brand=de,
                    reverified=adj_ratio >= required_ratio,
                )
                if best_brand is None or cand.delta_e_from_brand < best_brand.delta_e_from_brand:
                    best_brand = cand
            if best_brand is not None and all(
                c.foreground_hex != best_brand.foreground_hex for c in candidates
            ):
                candidates.append(best_brand)

        return candidates[: max(1, max_candidates)]


default_design_alternative_provider: DesignAlternativeProvider = CielabDesignAlternativeProvider()


def detect_text_band_boxes(rgb_or_gray: np.ndarray, *, min_width: int = 16) -> tuple[BBox, ...]:
    """Detect horizontal text-line bounding boxes via Sobel + morphological closing."""
    gray = cv2.cvtColor(rgb_or_gray, cv2.COLOR_RGB2GRAY) if rgb_or_gray.ndim == 3 else rgb_or_gray
    h, w = gray.shape
    if h < 16 or w < 16:
        return ()

    grad_x = cv2.Sobel(gray, ddepth=cv2.CV_16S, dx=1, dy=0, ksize=3)
    abs_grad = cv2.convertScaleAbs(grad_x)
    _, thresh = cv2.threshold(abs_grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kw = max(9, w // 25)
    kh = max(3, h // 80)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[BBox] = []
    for cnt in contours:
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bw >= min_width and 4 <= bh <= int(h * 0.45) and bw >= bh:
            boxes.append(BBox(x=int(bx), y=int(by), w=int(bw), h=int(bh)))

    boxes.sort()
    return tuple(boxes)


def segment_fg_bg_rgb(
    crop_rgb: np.ndarray,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Separate foreground glyph RGB and background RGB using Otsu bimodal thresholding."""
    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    pos_mask = mask > 0
    neg_mask = ~pos_mask
    if not np.any(pos_mask) or not np.any(neg_mask):
        med = tuple(round(float(x)) for x in np.median(crop_rgb.reshape(-1, 3), axis=0))
        return (med[0], med[1], med[2]), (med[0], med[1], med[2])

    pos_rgb = tuple(round(float(x)) for x in np.median(crop_rgb[pos_mask], axis=0))
    neg_rgb = tuple(round(float(x)) for x in np.median(crop_rgb[neg_mask], axis=0))
    if int(np.count_nonzero(pos_mask)) >= int(np.count_nonzero(neg_mask)):
        bg_rgb = (pos_rgb[0], pos_rgb[1], pos_rgb[2])
        fg_rgb = (neg_rgb[0], neg_rgb[1], neg_rgb[2])
    else:
        fg_rgb = (pos_rgb[0], pos_rgb[1], pos_rgb[2])
        bg_rgb = (neg_rgb[0], neg_rgb[1], neg_rgb[2])
    return fg_rgb, bg_rgb
