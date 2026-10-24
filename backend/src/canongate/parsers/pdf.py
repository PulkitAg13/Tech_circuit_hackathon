"""PDF Document, Table, Embedded Banner, and Hidden Micro-Text Parser (`parsers/pdf.py`).

Uses `pdfplumber` (MIT) with automatic fallback to `pypdf` (BSD-3):
1. Detects and linearizes PDF tables via `page.find_tables()` (bordered lattice tables)
   and `_extract_whitespace_aligned_tables()` (borderless whitespace/tab-aligned tables)
   via `TableGrid`, filtering bordered table bounding boxes out of the page before body
   text extraction so tabular numbers are never duplicated as mangled plain text.
2. Inspects `page.chars` for OWASP LLM01 indirect prompt-injection vectors:
   micro-font text (`size < 4.0` pt) or white-on-white fill colour
   (`(1, 1, 1)` or `(255, 255, 255)`), emitting `{source}/page[{p}]/hidden[0]`.
3. Splits remaining body text into paragraph `TextNode`s (`{source}/page[{p}]/p[{i}]`).
4. Extracts embedded raster images/banners from PDF pages via `pypdf` and routes
   them through `parse_banner_image` for CV + OCR inspection.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from canongate.domain.ast import ContentAST, Node, TextNode
from canongate.parsers.banner import parse_banner_image
from canongate.parsers.llm_table import MultiProviderJsonLLM
from canongate.parsers.tables import TableGrid, is_footnote_text

logger = logging.getLogger(__name__)

_PARA_SPLIT = re.compile(r"\n{2,}")
_BORDERLESS_ROW_RE = re.compile(r"\S+\s{2,}\S+")
_PDF_MEDIA_DIR = Path("/tmp/.canongate_pdf_media")


def _is_white_color(color: Any) -> bool:
    if not isinstance(color, (tuple, list)) or len(color) < 3:
        return False
    try:
        vals = [float(c) for c in color[:3]]
    except (ValueError, TypeError):
        return False
    return all(v >= 0.98 for v in vals) or all(v >= 250.0 for v in vals)


def _is_char_hidden(ch: dict[str, Any]) -> bool:
    try:
        size = float(ch.get("size", 10.0))
    except (ValueError, TypeError):
        size = 10.0
    if size < 4.0:
        return True
    return _is_white_color(ch.get("non_stroking_color"))


def _point_in_bboxes(
    x0: float,
    top: float,
    x1: float,
    bottom: float,
    bboxes: list[tuple[float, float, float, float]],
) -> bool:
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (top + bottom)
    return any(bx0 <= cx <= bx1 and btop <= cy <= bbottom for bx0, btop, bx1, bbottom in bboxes)


def _extract_whitespace_aligned_tables(raw_text: str) -> tuple[list[list[list[str]]], list[str]]:
    """Recover borderless multi-column tables from raw page text when vector lines are absent."""
    blocks = [b.strip() for b in _PARA_SPLIT.split(raw_text) if b.strip()]
    tables: list[list[list[str]]] = []
    remaining_blocks: list[str] = []

    for blk in blocks:
        lines = [ln.strip() for ln in blk.splitlines() if ln.strip()]
        multi_col_lines = [ln for ln in lines if _BORDERLESS_ROW_RE.search(ln)]
        if len(lines) >= 2 and len(multi_col_lines) >= 2:
            table_lines: list[str] = []
            for ln in lines:
                if _BORDERLESS_ROW_RE.search(ln) or is_footnote_text(ln):
                    table_lines.append(ln)
                else:
                    remaining_blocks.append(ln)
            grid: list[list[str]] = []
            for ln in table_lines:
                if is_footnote_text(ln):
                    grid.append([ln])
                else:
                    cells = [c.strip() for c in re.split(r"\s{2,}|\t+", ln) if c.strip()]
                    if cells:
                        grid.append(cells)
            if len(grid) >= 2 and max(len(r) for r in grid) >= 2:
                tables.append(grid)
                continue
        remaining_blocks.append(blk)

    return tables, remaining_blocks


def _extract_pdf_embedded_images(raw_bytes: bytes) -> list[Node]:
    """Extract embedded raster images from PDF pages using `pypdf` into `ImageNode`s + OCR."""
    extracted_nodes: list[Node] = []
    try:
        import pypdf  # type: ignore[import-untyped]

        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        _PDF_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        seen_digests: set[str] = set()
        for page in reader.pages:
            images = getattr(page, "images", None) or ()
            for img_file in images:
                blob = getattr(img_file, "data", b"")
                if not blob or len(blob) < 128:
                    continue
                digest = hashlib.sha256(blob).hexdigest()[:12]
                if digest in seen_digests:
                    continue
                try:
                    with Image.open(io.BytesIO(blob)) as im:
                        w, h = im.size
                        if w < 32 or h < 32:
                            continue
                        rgb_im = im.convert("RGB")
                        out_path = _PDF_MEDIA_DIR / f"{digest}_pdf_img.png"
                        if not out_path.is_file():
                            rgb_im.save(out_path, format="PNG")
                    seen_digests.add(digest)
                    img_ast = parse_banner_image(out_path, path=str(out_path), alt=None)
                    extracted_nodes.extend(img_ast.nodes)
                except (UnidentifiedImageError, OSError, ValueError):
                    continue
    except Exception:
        pass
    return extracted_nodes


def _parse_with_pypdf(
    raw_bytes: bytes,
    *,
    source: str,
    llm_client: MultiProviderJsonLLM | None = None,
) -> ContentAST:
    try:
        import pypdf  # type: ignore[import-untyped]

        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        nodes: list[Node] = []
        for p_idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            page_prefix = f"{source}/page[{p_idx}]"
            ws_tables, rem_blocks = _extract_whitespace_aligned_tables(text)
            for t_idx, raw_grid in enumerate(ws_tables):
                tbl_ast = TableGrid.from_raw_grid(
                    raw_grid,
                    source=f"{page_prefix}/table[{t_idx}]",
                    llm_client=llm_client,
                ).to_ast()
                nodes.extend(tbl_ast.nodes)
            for b_idx, block in enumerate(rem_blocks):
                cleaned = block.strip()
                if cleaned:
                    nodes.append(TextNode.from_text(cleaned, path=f"{page_prefix}/p[{b_idx}]"))
        nodes.extend(_extract_pdf_embedded_images(raw_bytes))
        return ContentAST(nodes=tuple(nodes))
    except Exception:
        logger.warning("Failed to parse PDF via pypdf fallback at %s", source)
        return ContentAST(nodes=())


def parse_pdf(
    source: str | Path | bytes,
    *,
    source_name: str = "pdf",
    llm_client: MultiProviderJsonLLM | None = None,
) -> ContentAST:
    """Parse a PDF file or byte buffer into a `ContentAST` of text, tables, and images."""
    try:
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.is_file():
                logger.warning("PDF file not found: %s", path)
                return ContentAST(nodes=())
            raw_bytes = path.read_bytes()
        elif isinstance(source, (bytes, bytearray, memoryview)):
            raw_bytes = bytes(source)
        else:
            return ContentAST(nodes=())
    except OSError:
        logger.warning("Failed to read PDF file at %s", source_name)
        return ContentAST(nodes=())

    if not raw_bytes:
        return ContentAST(nodes=())

    try:
        import pdfplumber  # type: ignore[import-untyped]
    except ImportError:
        return _parse_with_pypdf(raw_bytes, source=source_name, llm_client=llm_client)

    nodes: list[Node] = []
    try:
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            for p_idx, page in enumerate(pdf.pages):
                page_prefix = f"{source_name}/page[{p_idx}]"

                # 1. Extract hidden / micro-font characters (< 4pt or white-on-white)
                chars = getattr(page, "chars", None) or []
                hidden_chars = [str(c.get("text", "")) for c in chars if _is_char_hidden(c)]
                hidden_text = "".join(hidden_chars).strip()
                if hidden_text:
                    nodes.append(TextNode.from_text(hidden_text, path=f"{page_prefix}/hidden[0]"))

                # 2. Extract bordered lattice tables first
                table_bboxes: list[tuple[float, float, float, float]] = []
                found_tables = page.find_tables() if hasattr(page, "find_tables") else []

                for t_idx, tbl_obj in enumerate(found_tables):
                    bbox = getattr(tbl_obj, "bbox", None)
                    if bbox and len(bbox) == 4:
                        table_bboxes.append(
                            (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                        )
                    raw_grid = tbl_obj.extract()
                    if raw_grid:
                        tbl_ast = TableGrid.from_raw_grid(
                            raw_grid,
                            source=f"{page_prefix}/table[{t_idx}]",
                            llm_client=llm_client,
                        ).to_ast()
                        nodes.extend(tbl_ast.nodes)

                # 3. Filter out hidden chars and table-interior chars before extracting paragraphs
                body_page = page
                if (table_bboxes or hidden_text) and hasattr(page, "filter"):
                    body_page = page.filter(
                        lambda obj, tb=table_bboxes: (
                            obj.get("object_type") != "char"
                            or (
                                not _is_char_hidden(obj)
                                and not _point_in_bboxes(
                                    float(obj.get("x0", 0.0)),
                                    float(obj.get("top", 0.0)),
                                    float(obj.get("x1", 0.0)),
                                    float(obj.get("bottom", 0.0)),
                                    tb,
                                )
                            )
                        )
                    )

                raw_text = (body_page.extract_text() or "").strip()
                if raw_text:
                    if not found_tables:
                        ws_tables, rem_blocks = _extract_whitespace_aligned_tables(raw_text)
                        for t_idx, raw_grid in enumerate(ws_tables):
                            tbl_ast = TableGrid.from_raw_grid(
                                raw_grid,
                                source=f"{page_prefix}/table[{t_idx}]",
                                llm_client=llm_client,
                            ).to_ast()
                            nodes.extend(tbl_ast.nodes)
                        for b_idx, block in enumerate(rem_blocks):
                            cleaned = block.strip()
                            if cleaned:
                                nodes.append(
                                    TextNode.from_text(cleaned, path=f"{page_prefix}/p[{b_idx}]")
                                )
                    else:
                        for b_idx, block in enumerate(_PARA_SPLIT.split(raw_text)):
                            cleaned = block.strip()
                            if cleaned:
                                nodes.append(
                                    TextNode.from_text(cleaned, path=f"{page_prefix}/p[{b_idx}]")
                                )
        nodes.extend(_extract_pdf_embedded_images(raw_bytes))
    except Exception:
        logger.warning("pdfplumber failed on %s; attempting pypdf fallback", source_name)
        return _parse_with_pypdf(raw_bytes, source=source_name, llm_client=llm_client)

    return ContentAST(nodes=tuple(nodes))
