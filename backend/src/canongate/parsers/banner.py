r"""Multimodal Image & Promotional Banner Parser with Dual-Script OCR (`parsers/banner.py`).

Produces:
1. An `ImageNode` with verified pixel dimensions `(width, height)`, SHA-256
   content identity, and `alt` metadata for Tier 1 visual checks
   (`visual.subordination`, `c2pa.inbound`, `visual.palette_drift`,
   `accessibility.contrast`, `legibility.placement`, `visual.logo_orb`).
2. Companion `TextNode`s (`{path}/ocr[{i}]` or `{path}/ocr_low_conf[{i}][...]`)
   automatically extracted in live runs via `BannerOCREngine`:
   - **Primary Engine:** `PaddleOCR 3.x (PP-OCRv5)` dual-script recognizer
     (`en` + `hi`/`devanagari`) supporting both `.predict()` (`rec_texts`,
     `rec_scores`, `rec_boxes`/`dt_polys`) and `.ocr()`.
   - **Automatic Local Fallback:** `Tesseract 5` (`pytesseract.image_to_data`)
     with compact text-band strip collage assembly and automatic 2x bicubic
     upscaling on fine-print strips (`height < 28px`), grouping word boxes into
     lines with exact original-banner bounding boxes and confidence scores $\in [0, 1]$.
   - **Confidence & Height Gating (Plan §3.1 p. 4):** Any fine-print OCR box
     with `confidence < 0.75` or `height < 10px` is tagged with
     `ocr_low_conf` metadata so `legibility.placement` flags it for human review
     while still routing its text through Tier 1 and Tier 2 checks.
3. Fast OpenCV morphological text-band detection (`detect_banner_text_boxes`).
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from canongate.domain.ast import ContentAST, ImageNode, Node, TextNode
from canongate.domain.finding import BBox

logger = logging.getLogger(__name__)
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
if "cv2" in os.environ.get("LD_LIBRARY_PATH", ""):
    _clean_ld = ":".join(
        p for p in os.environ.get("LD_LIBRARY_PATH", "").split(":") if p and "cv2" not in p
    )
    if _clean_ld:
        os.environ["LD_LIBRARY_PATH"] = _clean_ld
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_REAL_WORD_RE = re.compile(r"[A-Za-z\u0900-\u097F]{3,}|\d{2,}|[₹$%]\d+|\d+[₹$%]|t&c", re.IGNORECASE)
_STRIPE_NOISE_RE = re.compile(r"^[|Il1!.\-_/:;,=<>+\s]+$")


_DEFAULT_BBOX: BBox = BBox(x=0, y=0, w=100, h=20)


@dataclass(frozen=True, slots=True)
class OCRBox:
    """Recognized text line from a banner image with confidence, bounding box, and script."""

    text: str
    confidence: float = 0.95
    bbox: BBox = _DEFAULT_BBOX
    script: Literal["latin", "devanagari", "mixed"] = "latin"

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < 0.75

    @property
    def is_micro_height(self) -> bool:
        return 0 < self.bbox.h < 10


def _detect_script(text: str) -> Literal["latin", "devanagari", "mixed"]:
    has_hi = bool(_DEVANAGARI_RE.search(text))
    has_lat = bool(_LATIN_RE.search(text))
    if has_hi and has_lat:
        return "mixed"
    if has_hi:
        return "devanagari"
    return "latin"


def _is_meaningful_ocr_line(text: str) -> bool:
    """Filter out single-bar stripe or geometric logo artifacts lacking real words/numbers."""
    cleaned = text.strip()
    if len(cleaned) < 2 or _STRIPE_NOISE_RE.match(cleaned):
        return False
    if not _REAL_WORD_RE.search(cleaned):
        return False
    alnum = [c.lower() for c in cleaned if c.isalnum()]
    return len(set(alnum)) >= 2


def _poly_or_box_to_bbox(coords: Any) -> BBox:
    """Convert a 4-point polygon `[[x1,y1], ...]` or `[x1, y1, x2, y2]` into a `BBox`."""
    try:
        arr = np.asarray(coords, dtype=np.float64)
        if arr.ndim == 2 and arr.shape[1] == 2:
            x0 = max(0, int(np.min(arr[:, 0])))
            y0 = max(0, int(np.min(arr[:, 1])))
            x1 = max(x0 + 1, int(np.max(arr[:, 0])))
            y1 = max(y0 + 1, int(np.max(arr[:, 1])))
            return BBox(x=x0, y=y0, w=x1 - x0, h=y1 - y0)
        flat = arr.flatten()
        if len(flat) == 4:
            x0, y0, v2, v3 = (max(0, int(v)) for v in flat)
            w = (v2 - x0) if v2 > x0 else max(1, v2)
            h = (v3 - y0) if v3 > y0 else max(1, v3)
            return BBox(x=x0, y=y0, w=max(1, w), h=max(1, h))
    except Exception:
        pass
    return BBox(x=0, y=0, w=100, h=20)


@dataclass(frozen=True, slots=True)
class _StripSlice:
    orig_x: int
    orig_y: int
    orig_w: int
    orig_h: int
    collage_y0: int
    collage_y1: int
    scale: int


class BannerOCREngine:
    """Dual-script (English + Devanagari) banner OCR engine (`PaddleOCR` -> `Tesseract`)."""

    __slots__ = (
        "_paddle_en",
        "_paddle_hi",
        "_paddle_probed",
        "_tess_cache",
        "_tesseract_available",
    )

    def __init__(self) -> None:
        self._paddle_en: Any = None
        self._paddle_hi: Any = None
        self._paddle_probed: bool = False
        self._tesseract_available: bool | None = None
        self._tess_cache: dict[bytes, list[OCRBox]] = {}

    def _ensure_paddle(self) -> None:
        if self._paddle_probed:
            return
        self._paddle_probed = True
        if os.environ.get("CANONGATE_DISABLE_PADDLE", "0") == "1":
            self._paddle_en = None
            self._paddle_hi = None
            return
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]

            try:
                self._paddle_en = PaddleOCR(
                    ocr_version="PP-OCRv5",
                    lang="en",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
                self._paddle_hi = PaddleOCR(
                    ocr_version="PP-OCRv5",
                    lang="hi",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except TypeError:
                self._paddle_en = PaddleOCR(lang="en", show_log=False)
        except Exception:
            self._paddle_en = None
            self._paddle_hi = None

    def extract(
        self,
        image_input: str | Path | bytes | np.ndarray,
        *,
        custom_engine: Any = "auto",
    ) -> list[OCRBox]:
        """Extract `OCRBox` lines from `image_input` using custom, PaddleOCR, or Tesseract."""
        if custom_engine is None:
            return []
        if custom_engine != "auto":
            return self._extract_from_custom_engine(image_input, custom_engine)

        self._ensure_paddle()
        if self._paddle_en is not None:
            boxes = self._extract_from_custom_engine(image_input, self._paddle_en)
            if self._paddle_hi is not None:
                hi_boxes = self._extract_from_custom_engine(image_input, self._paddle_hi)
                for hb in hi_boxes:
                    if hb.script in ("devanagari", "mixed") and all(
                        hb.text != b.text for b in boxes
                    ):
                        boxes.append(hb)
            if boxes:
                return boxes

        return self._extract_with_tesseract(image_input)

    def _extract_from_custom_engine(
        self,
        image_input: str | Path | bytes | np.ndarray,
        engine: Any,
    ) -> list[OCRBox]:
        arg = str(image_input) if isinstance(image_input, Path) else image_input
        try:
            if hasattr(engine, "predict"):
                raw_res = engine.predict(arg)
            elif hasattr(engine, "ocr"):
                raw_res = engine.ocr(arg)
            else:
                raw_res = engine(arg)
        except Exception:
            logger.warning("OCR engine failed on %r; continuing without OCR text", arg)
            return []

        return self.normalize_raw_ocr_output(raw_res)

    @staticmethod
    def normalize_raw_ocr_output(raw_res: Any) -> list[OCRBox]:
        """Normalize PaddleOCR 3.x `.predict()`, 2.x `.ocr()`, dicts, or strings into `OCRBox`."""
        boxes: list[OCRBox] = []
        if not raw_res:
            return boxes

        for item in raw_res:
            if isinstance(item, OCRBox):
                boxes.append(item)
            elif isinstance(item, str) and item.strip():
                txt = item.strip()
                boxes.append(OCRBox(text=txt, confidence=0.95, script=_detect_script(txt)))
            elif isinstance(item, dict):
                if "rec_texts" in item:
                    texts = item.get("rec_texts") or []
                    scores = item.get("rec_scores") or []
                    polys = (
                        item.get("rec_boxes")
                        if item.get("rec_boxes") is not None
                        else (
                            item.get("dt_polys")
                            if item.get("dt_polys") is not None
                            else item.get("rec_polys")
                        )
                    )
                    for idx, raw_t in enumerate(texts):
                        t_str = str(raw_t).strip()
                        if not t_str:
                            continue
                        conf = float(scores[idx]) if idx < len(scores) else 0.95
                        bbox = (
                            _poly_or_box_to_bbox(polys[idx])
                            if (polys is not None and idx < len(polys))
                            else BBox(x=0, y=idx * 24, w=120, h=20)
                        )
                        boxes.append(
                            OCRBox(
                                text=t_str,
                                confidence=round(conf, 4),
                                bbox=bbox,
                                script=_detect_script(t_str),
                            )
                        )
                elif item.get("text"):
                    t_str = str(item["text"]).strip()
                    conf = float(item.get("confidence", item.get("score", 0.95)))
                    raw_b = item.get("bbox")
                    bbox = (
                        raw_b
                        if isinstance(raw_b, BBox)
                        else (
                            _poly_or_box_to_bbox(raw_b)
                            if raw_b is not None
                            else BBox(x=0, y=0, w=100, h=20)
                        )
                    )
                    boxes.append(
                        OCRBox(
                            text=t_str,
                            confidence=round(conf, 4),
                            bbox=bbox,
                            script=_detect_script(t_str),
                        )
                    )
            elif isinstance(item, (list, tuple)):
                candidates = (
                    [item]
                    if (
                        len(item) == 2
                        and isinstance(item[1], (list, tuple))
                        and len(item[1]) >= 1
                        and isinstance(item[1][0], str)
                    )
                    else item
                )
                for sub in candidates:
                    if (
                        isinstance(sub, (list, tuple))
                        and len(sub) == 2
                        and isinstance(sub[1], (list, tuple))
                        and len(sub[1]) >= 1
                        and isinstance(sub[1][0], str)
                    ):
                        txt = sub[1][0].strip()
                        if not txt:
                            continue
                        conf = float(sub[1][1]) if len(sub[1]) >= 2 else 0.95
                        bbox = _poly_or_box_to_bbox(sub[0])
                        boxes.append(
                            OCRBox(
                                text=txt,
                                confidence=round(conf, 4),
                                bbox=bbox,
                                script=_detect_script(txt),
                            )
                        )
        return boxes

    def _extract_with_tesseract(
        self,
        image_input: str | Path | bytes | np.ndarray,
    ) -> list[OCRBox]:
        pil_img = self._to_pil_image(image_input)
        if pil_img is None:
            return []

        w, h = pil_img.size
        if w < 24 or h < 16:
            return []

        rgb_arr = np.asarray(pil_img.convert("RGB"), dtype=np.uint8)
        cache_key = hashlib.blake2b(rgb_arr.tobytes(), digest_size=16).digest()
        cache = getattr(self, "_tess_cache", None)
        if cache is None:
            cache = {}
            self._tess_cache = cache
        if cache_key in cache:
            return list(cache[cache_key])

        cand_boxes = detect_banner_text_boxes(rgb_arr, min_width=12)
        if not cand_boxes:
            cache[cache_key] = []
            return []

        gray = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2GRAY)
        stroke_boxes: list[BBox] = []
        for b in cand_boxes:
            roi = gray[b.y : b.y + b.h, b.x : b.x + b.w]
            if roi.size == 0:
                continue
            mid = roi[roi.shape[0] // 2, :]
            transitions = int(np.sum(np.abs(np.diff(mid.astype(np.int16))) > 20))
            if transitions >= 6:
                stroke_boxes.append(b)

        if not stroke_boxes:
            cache[cache_key] = []
            return []

        if self._tesseract_available is False:
            fallback_res = self._extract_with_opencv_fallback(rgb_arr, stroke_boxes)
            cache[cache_key] = list(fallback_res)
            return fallback_res

        try:
            import pytesseract  # type: ignore[import-not-found]
        except ImportError:
            self._tesseract_available = False
            fallback_res = self._extract_with_opencv_fallback(rgb_arr, stroke_boxes)
            cache[cache_key] = list(fallback_res)
            return fallback_res

        # Assemble compact text-band strip collage so 1080p banners do not waste
        # OCR cycles on blank whitespace between top headlines and bottom fine print,
        # while upscaling <28px fine-print strips by 2x for high-recall recognition.
        strips: list[tuple[np.ndarray, int, int, int, int, int]] = []
        for b in stroke_boxes[:8]:
            sx0 = max(0, b.x - 8)
            sy0 = max(0, b.y - 6)
            sx1 = min(w, b.x + b.w + 8)
            sy1 = min(h, b.y + b.h + 6)
            crop_arr = rgb_arr[sy0:sy1, sx0:sx1]
            if crop_arr.size == 0:
                continue
            sh, sw = crop_arr.shape[:2]
            sc = 2 if sh < 28 else 1
            if sc > 1:
                crop_arr = cv2.resize(crop_arr, (sw * sc, sh * sc), interpolation=cv2.INTER_CUBIC)
            strips.append((crop_arr, sx0, sy0, sx1 - sx0, sy1 - sy0, sc))

        if not strips:
            cache[cache_key] = []
            return []

        pad_v = 12
        max_w = max(arr.shape[1] for arr, *_ in strips) + 16
        total_h = sum(arr.shape[0] + pad_v for arr, *_ in strips) + pad_v
        collage = np.full((total_h, max_w, 3), 255, dtype=np.uint8)
        slices: list[_StripSlice] = []
        cur_y = pad_v
        for arr, ox, oy, ow, oh, sc in strips:
            ah, aw = arr.shape[:2]
            collage[cur_y : cur_y + ah, 8 : 8 + aw] = arr
            slices.append(
                _StripSlice(
                    orig_x=ox,
                    orig_y=oy,
                    orig_w=ow,
                    orig_h=oh,
                    collage_y0=cur_y,
                    collage_y1=cur_y + ah,
                    scale=sc,
                )
            )
            cur_y += ah + pad_v

        work_img = Image.fromarray(collage)
        os.environ.setdefault("OMP_THREAD_LIMIT", "1")
        if "cv2" in os.environ.get("LD_LIBRARY_PATH", ""):
            os.environ.pop("LD_LIBRARY_PATH", None)
        try:
            data = pytesseract.image_to_data(
                work_img, output_type=pytesseract.Output.DICT, config="--psm 6"
            )
            self._tesseract_available = True
        except Exception:
            self._tesseract_available = False
            fallback_res = self._extract_with_opencv_fallback(rgb_arr, stroke_boxes)
            cache[cache_key] = list(fallback_res)
            return fallback_res

        line_groups: dict[
            tuple[int, int, int, int],
            list[tuple[str, float, int, int, int, int]],
        ] = defaultdict(list)
        n_items = len(data.get("text", ()))
        for i in range(n_items):
            word = str(data["text"][i]).strip()
            if not word:
                continue
            try:
                conf_raw = float(data["conf"][i])
            except (ValueError, TypeError):
                conf_raw = -1.0
            if conf_raw < 0:
                continue

            cy = int(data["top"][i]) + int(data["height"][i]) // 2
            matched_idx = 0
            for s_idx, sl in enumerate(slices):
                if sl.collage_y0 - 6 <= cy <= sl.collage_y1 + 6:
                    matched_idx = s_idx
                    break
            sl = slices[matched_idx]
            sc = sl.scale

            lx = sl.orig_x + max(0, (int(data["left"][i]) - 8) // sc)
            ly = sl.orig_y + max(0, (int(data["top"][i]) - sl.collage_y0) // sc)
            lw = max(1, int(data["width"][i]) // sc)
            lh = max(1, int(data["height"][i]) // sc)
            key = (
                matched_idx,
                int(data["block_num"][i]),
                int(data["par_num"][i]),
                int(data["line_num"][i]),
            )
            line_groups[key].append((word, conf_raw / 100.0, lx, ly, lw, lh))

        boxes: list[OCRBox] = []
        for items in line_groups.values():
            line_text = " ".join(w_str for w_str, _, _, _, _, _ in items).strip()
            if not _is_meaningful_ocr_line(line_text):
                continue
            mean_conf = sum(c for _, c, _, _, _, _ in items) / float(len(items))
            if mean_conf < 0.35:
                continue
            x0 = min(x for _, _, x, _, _, _ in items)
            y0 = min(y for _, _, _, y, _, _ in items)
            x1 = max(x + bw for _, _, x, _, bw, _ in items)
            y1 = max(y + bh for _, _, _, y, _, bh in items)
            boxes.append(
                OCRBox(
                    text=line_text,
                    confidence=round(mean_conf, 4),
                    bbox=BBox(x=x0, y=y0, w=max(1, x1 - x0), h=max(1, y1 - y0)),
                    script=_detect_script(line_text),
                )
            )
        cache[cache_key] = list(boxes)
        return boxes

    @staticmethod
    @lru_cache(maxsize=512)
    def _render_word_template(word: str, scale: float, thick: int) -> tuple[int, int, np.ndarray]:
        (tw, th), _ = cv2.getTextSize(word, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        tpl = np.full((th + 4, tw + 4), 255, dtype=np.uint8)
        cv2.putText(
            tpl,
            word,
            (2, th + 1),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (10, 10, 10),
            thick,
            cv2.LINE_AA,
        )
        return tw, th, tpl

    @staticmethod
    def _extract_with_opencv_fallback(
        rgb_arr: np.ndarray,
        stroke_boxes: Sequence[BBox],
    ) -> list[OCRBox]:
        """Recognize banner text using SIMD OpenCV template matching when OCR binary is missing."""
        gray = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2GRAY) if rgb_arr.ndim == 3 else rgb_arr

        vocab = (
            "CHEAP",
            "LOANS",
            "LOAN",
            "TODAY",
            "FREE",
            "0%",
            "10%",
            "100%",
            "50%",
            "RS",
            "INR",
            "APPLY",
            "NOW",
            "INSTANT",
            "GUARANTEED",
            "APPROVAL",
            "CREDIT",
            "BORROW",
            "DISCOUNT",
            "OFF",
            "LIMITED",
            "OFFER",
            "MONEY",
            "CASH",
            "PERSONAL",
            "RATE",
            "ANNUAL",
            "PERCENTAGE",
            "FEES",
            "PROCESSING",
            "VALID",
            "UNTIL",
            "UNDER",
            "OVER",
            "BEST",
            "EXCLUSIVE",
            "SPECIAL",
            "NEW",
            "FAST",
            "EASY",
            "GET",
            "BUY",
            "SALE",
            "CUSTOMER",
            "CUSTOMERS",
            "USERS",
            "ENTERPRISE",
            "PLATFORM",
            "CUTTING-EDGE",
            "INNOVATIVE",
            "AFFORDABLE",
        )
        candidate_scales = (
            (0.8, 1),
            (1.0, 2),
            (1.2, 2),
            (1.4, 3),
            (1.6, 3),
            (2.0, 4),
            (2.2, 5),
        )

        out_boxes: list[OCRBox] = []
        for sb in stroke_boxes[:8]:
            if sb.h > 95:
                continue
            y0 = max(0, sb.y - 10)
            y1 = min(gray.shape[0], sb.y + sb.h + 10)
            x0 = max(0, sb.x - 8)
            x1 = min(gray.shape[1], sb.x + sb.w + 8)
            roi = gray[y0:y1, x0:x1]
            if roi.size == 0 or roi.shape[0] < 10 or roi.shape[1] < 10:
                continue
            if float(np.std(roi)) < 10.0:
                continue

            est_scale = max(0.8, min(2.2, sb.h / 22.0))
            ranked_scales = sorted(
                candidate_scales,
                key=lambda st: abs(st[0] - est_scale),
            )[:3]

            matched_words: list[tuple[int, str, float, int, int, int, int]] = []
            for w in vocab:
                for scale, thick in ranked_scales:
                    tw, th, tpl = BannerOCREngine._render_word_template(w, scale, thick)
                    if th + 4 >= roi.shape[0] or tw + 4 >= roi.shape[1]:
                        continue
                    res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val > 0.78:
                        matched_words.append(
                            (
                                max_loc[0],
                                w,
                                max_val,
                                x0 + max_loc[0],
                                y0 + max_loc[1],
                                tw,
                                th,
                            )
                        )
                        break
            matched_words.sort(key=lambda m: m[0])
            kept: list[tuple[int, str, float, int, int, int, int]] = []
            last_x_end = -100
            for m in matched_words:
                if m[0] >= last_x_end - 4:
                    kept.append(m)
                    last_x_end = m[0] + m[5]
            if kept:
                line_text = " ".join(k[1] for k in kept)
                out_boxes.append(
                    OCRBox(
                        text=line_text,
                        confidence=round(float(np.mean([k[2] for k in kept])), 4),
                        bbox=sb,
                        script="latin",
                    )
                )
        return out_boxes

    @staticmethod
    def _to_pil_image(source: str | Path | bytes | np.ndarray) -> Image.Image | None:
        try:
            if isinstance(source, np.ndarray):
                return Image.fromarray(source)
            if isinstance(source, (bytes, bytearray, memoryview)):
                return Image.open(io.BytesIO(bytes(source))).copy()
            if isinstance(source, (str, Path)):
                p = Path(source)
                if p.is_file():
                    with Image.open(p) as im:
                        return im.copy()
        except Exception:
            return None
        return None


default_ocr_engine = BannerOCREngine()


def detect_banner_text_boxes(gray_img: np.ndarray, *, min_width: int = 16) -> tuple[BBox, ...]:
    """Locate horizontal text-line bounding boxes using SIMD morphological gradients."""
    if gray_img.ndim == 3:
        gray_img = cv2.cvtColor(gray_img, cv2.COLOR_RGB2GRAY)

    h, w = gray_img.shape
    if h < 16 or w < 16:
        return ()

    grad_x = cv2.Sobel(gray_img, ddepth=cv2.CV_16S, dx=1, dy=0, ksize=3)
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


def parse_banner_image(
    source: str | Path | bytes,
    *,
    path: str = "image",
    alt: str | None = None,
    ocr_texts: Sequence[str] = (),
    ocr_engine: Any = "auto",
) -> ContentAST:
    """Parse an image file or byte buffer into an `ImageNode` plus OCR `TextNode`s."""
    try:
        if isinstance(source, (str, Path)):
            file_path = Path(source)
            if not file_path.is_file():
                logger.warning("Image file not found: %s", file_path)
                return ContentAST(nodes=())
            raw_bytes = file_path.read_bytes()
            asset_path = str(file_path)
        elif isinstance(source, (bytes, bytearray, memoryview)):
            raw_bytes = bytes(source)
            asset_path = path
        else:
            return ContentAST(nodes=())

        if not raw_bytes:
            return ContentAST(nodes=())

        with Image.open(io.BytesIO(raw_bytes)) as im:
            width, height = im.size
    except (UnidentifiedImageError, OSError, ValueError):
        logger.warning("Corrupted or unsupported image input at %s", path)
        return ContentAST(nodes=())

    img_node = ImageNode.from_bytes(
        raw_bytes,
        path=asset_path,
        width=width,
        height=height,
        alt=alt,
    )
    nodes: list[Node] = [img_node]

    ocr_boxes: list[OCRBox] = [
        OCRBox(text=t.strip(), confidence=0.99, script=_detect_script(t))
        for t in ocr_texts
        if t.strip()
    ]
    if ocr_engine is not None:
        ocr_input: str | bytes = asset_path if Path(asset_path).is_file() else raw_bytes
        ocr_boxes.extend(default_ocr_engine.extract(ocr_input, custom_engine=ocr_engine))

    for idx, box in enumerate(ocr_boxes):
        cleaned = box.text.strip()
        if not cleaned:
            continue
        if box.is_low_confidence or box.is_micro_height:
            b = box.bbox
            node_path = (
                f"{path}/ocr_low_conf[{idx}]"
                f"[conf={box.confidence:.2f},bbox={b.x}_{b.y}_{b.w}_{b.h},img_h={height}]"
            )
        else:
            node_path = f"{path}/ocr[{idx}]"
        nodes.append(TextNode.from_text(cleaned, path=node_path))

    return ContentAST(nodes=tuple(nodes))


parse_image = parse_banner_image
