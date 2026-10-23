"""PDF Document, Table, and Hidden Micro-Text Parser (`parsers/pdf.py`).

Uses `pdfplumber` (MIT) with automatic fallback to `pypdf` (BSD-3):
1. Detects and linearizes PDF tables via `page.find_tables()` and `TableGrid`,
   filtering table bounding boxes out of the page before body text extraction so
   tabular numbers are never duplicated as mangled plain text.
2. Inspects `page.chars` for OWASP LLM01 indirect prompt-injection vectors:
   micro-font text (`size < 4.0` pt) or white-on-white fill colour
   (`(1, 1, 1)` or `(255, 255, 255)`), emitting `{source}/page[{p}]/hidden[0]`.
3. Splits remaining body text into paragraph `TextNode`s (`{source}/page[{p}]/p[{i}]`).
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any

from canongate.domain.ast import ContentAST, Node, TextNode
from canongate.parsers.tables import TableGrid

logger = logging.getLogger(__name__)

_PARA_SPLIT = re.compile(r"\n{2,}")


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
    x0: float, top: float, x1: float, bottom: float, bboxes: list[tuple[float, float, float, float]]
) -> bool:
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (top + bottom)
    return any(bx0 <= cx <= bx1 and btop <= cy <= bbottom for bx0, btop, bx1, bbottom in bboxes)


def _parse_with_pypdf(raw_bytes: bytes, *, source: str) -> ContentAST:
    try:
        import pypdf  # type: ignore[import-untyped]

        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        nodes: list[Node] = []
        for p_idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            for b_idx, block in enumerate(_PARA_SPLIT.split(text)):
                cleaned = block.strip()
                if cleaned:
                    nodes.append(
                        TextNode.from_text(cleaned, path=f"{source}/page[{p_idx}]/p[{b_idx}]")
                    )
        return ContentAST(nodes=tuple(nodes))
    except Exception:
        logger.warning("Failed to parse PDF via pypdf fallback at %s", source)
        return ContentAST(nodes=())


def parse_pdf(
    source: str | Path | bytes,
    *,
    source_name: str = "pdf",
) -> ContentAST:
    """Parse a PDF file or byte buffer into a `ContentAST` of paragraphs, tables, and hidden text.

    Fault-tolerant: returns an empty `ContentAST` if the PDF is missing, empty, or corrupted.
    """
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
        return _parse_with_pypdf(raw_bytes, source=source_name)

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
                    nodes.append(
                        TextNode.from_text(hidden_text, path=f"{page_prefix}/hidden[0]")
                    )

                # 2. Extract tables and record their bounding boxes to avoid text duplication
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
                            raw_grid, source=f"{page_prefix}/table[{t_idx}]"
                        ).to_ast()
                        nodes.extend(tbl_ast.nodes)

                # 3. Filter out hidden chars and table-interior chars before extracting paragraphs
                body_page = page
                if (table_bboxes or hidden_text) and hasattr(page, "filter"):
                    body_page = page.filter(
                        lambda obj: obj.get("object_type") != "char"
                        or (
                            not _is_char_hidden(obj)
                            and not _point_in_bboxes(
                                float(obj.get("x0", 0.0)),
                                float(obj.get("top", 0.0)),
                                float(obj.get("x1", 0.0)),
                                float(obj.get("bottom", 0.0)),
                                table_bboxes,
                            )
                        )
                    )

                raw_text = (body_page.extract_text() or "").strip()
                if raw_text:
                    for b_idx, block in enumerate(_PARA_SPLIT.split(raw_text)):
                        cleaned = block.strip()
                        if cleaned:
                            nodes.append(
                                TextNode.from_text(cleaned, path=f"{page_prefix}/p[{b_idx}]")
                            )
    except Exception:
        logger.warning("pdfplumber failed on %s; attempting pypdf fallback", source_name)
        return _parse_with_pypdf(raw_bytes, source=source_name)

    return ContentAST(nodes=tuple(nodes))
