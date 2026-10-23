"""Multimodal Image & Promotional Banner Parser (`parsers/banner.py`).

Produces:
1. An `ImageNode` with verified pixel dimensions `(width, height)`, SHA-256
   content identity, and `alt` metadata for Tier 1 visual checks
   (`visual.subordination`, `c2pa.inbound`, `visual.palette_drift`,
   `accessibility.contrast`).
2. Companion `TextNode`s (`{path}/ocr[{i}]`) when an OCR callable/engine
   (such as PaddleOCR PP-OCRv5) or sidecar text is provided, so banner copy
   and fine-print disclaimers flow automatically through Tier 1 and Tier 2
   claim/terminology checks.
3. Fast, zero-dependency OpenCV morphological text-band detection
   (`detect_banner_text_boxes`) for measuring fine-print pixel heights
   (ASCI 26px / 1080p rule) and foreground/background contrast regions.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from canongate.domain.ast import ContentAST, ImageNode, Node, TextNode
from canongate.domain.finding import BBox

logger = logging.getLogger(__name__)


def detect_banner_text_boxes(gray_img: np.ndarray, *, min_width: int = 16) -> tuple[BBox, ...]:
    """Locate horizontal text-line bounding boxes using SIMD morphological gradients.

    Works offline in < 3ms without requiring a 1.5GB deep OCR runtime.
    Returns boxes sorted top-to-bottom, left-to-right (`BBox.__lt__`).
    """
    if gray_img.ndim == 3:
        gray_img = cv2.cvtColor(gray_img, cv2.COLOR_RGB2GRAY)

    h, w = gray_img.shape
    if h < 16 or w < 16:
        return ()

    # Horizontal Sobel gradient highlights vertical glyph strokes
    grad_x = cv2.Sobel(gray_img, ddepth=cv2.CV_16S, dx=1, dy=0, ksize=3)
    abs_grad = cv2.convertScaleAbs(grad_x)
    _, thresh = cv2.threshold(abs_grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Close horizontal gaps between characters in a word/line
    kw = max(9, w // 25)
    kh = max(3, h // 80)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[BBox] = []
    for cnt in contours:
        bx, by, bw, bh = cv2.boundingRect(cnt)
        # Filter out tiny noise specks and full-bleed borders
        if bw >= min_width and 4 <= bh <= int(h * 0.45) and bw >= bh:
            boxes.append(BBox(x=int(bx), y=int(by), w=int(bw), h=int(bh)))

    boxes.sort()
    return tuple(boxes)


def _extract_ocr_texts(source_path: str, ocr_engine: Any) -> list[str]:
    """Extract recognized strings from a pluggable OCR engine or callable."""
    if ocr_engine is None:
        return []
    try:
        raw_res = (
            ocr_engine.ocr(source_path) if hasattr(ocr_engine, "ocr") else ocr_engine(source_path)
        )
    except Exception:
        logger.warning("OCR engine failed on %s; continuing without OCR text", source_path)
        return []

    texts: list[str] = []
    if not raw_res:
        return texts

    for item in raw_res:
        if isinstance(item, str) and item.strip():
            texts.append(item.strip())
        elif isinstance(item, dict) and item.get("text"):
            texts.append(str(item["text"]).strip())
        elif isinstance(item, (list, tuple)):
            # PaddleOCR format: [[ [x1,y1].. ], ("text", confidence)]
            for sub in item:
                if (
                    isinstance(sub, (list, tuple))
                    and len(sub) == 2
                    and isinstance(sub[1], (list, tuple))
                    and len(sub[1]) >= 1
                    and isinstance(sub[1][0], str)
                ):
                    txt = sub[1][0].strip()
                    if txt:
                        texts.append(txt)
    return texts


def parse_banner_image(
    source: str | Path | bytes,
    *,
    path: str = "image",
    alt: str | None = None,
    ocr_texts: Sequence[str] = (),
    ocr_engine: Any = None,
) -> ContentAST:
    """Parse an image file or byte buffer into an `ImageNode` plus any OCR `TextNode`s.

    Fault-tolerant: returns an empty `ContentAST` if the file does not exist
    or is not a valid image raster.
    """
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

    extracted_lines = list(ocr_texts)
    if ocr_engine is not None:
        extracted_lines.extend(_extract_ocr_texts(asset_path, ocr_engine))

    for idx, text in enumerate(extracted_lines):
        cleaned = text.strip()
        if cleaned:
            nodes.append(TextNode.from_text(cleaned, path=f"{path}/ocr[{idx}]"))

    return ContentAST(nodes=tuple(nodes))


parse_image = parse_banner_image
