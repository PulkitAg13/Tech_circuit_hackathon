"""Microsoft Word (`.docx`) Document-Order Parser (`parsers/docx.py`).

Uses `python-docx` (`Document.iter_inner_content()`) to traverse paragraphs and
tables in exact document reading order:
1. Preserves headings and body paragraphs (`{source}/p[{i}]`).
2. Linearizes tables (including nested tables and horizontally merged cells)
   via `TableGrid` so RBI Key Fact Statement (KFS) fee/APR schedules retain
   column headers and footnotes (`{source}/table[{t}]/r[{r}]`).
3. Extracts embedded raster images from package relationships into disk-backed
   `ImageNode`s and OCR `TextNode`s via `parse_banner_image`.
"""

from __future__ import annotations

import hashlib
import io
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from canongate.domain.ast import ContentAST, Node, TextNode
from canongate.parsers.banner import parse_banner_image
from canongate.parsers.tables import TableGrid

logger = logging.getLogger(__name__)

_DOCX_MEDIA_DIR = Path("/tmp/.canongate_docx_media")


def _iter_docx_blocks(container: Any) -> Iterator[tuple[str, Any]]:
    """Yield `("p", Paragraph)` or `("tbl", Table)` in exact document order."""
    if hasattr(container, "iter_inner_content"):
        for item in container.iter_inner_content():
            cls_name = type(item).__name__
            if cls_name == "Paragraph":
                yield ("p", item)
            elif cls_name == "Table":
                yield ("tbl", item)
        return

    for p in getattr(container, "paragraphs", ()):
        yield ("p", p)
    for t in getattr(container, "tables", ()):
        yield ("tbl", t)


def _extract_docx_table_grids(table: Any) -> Iterator[list[list[str]]]:
    """Extract 2D string grids from a `docx.table.Table` and any nested cell tables."""
    grid: list[list[str]] = []
    nested_tables: list[Any] = []

    for row in table.rows:
        row_cells: list[str] = []
        seen_tc_ids: set[int] = set()
        for cell in row.cells:
            tc_id = id(cell._tc)
            if tc_id not in seen_tc_ids:
                seen_tc_ids.add(tc_id)
                for sub_tbl in getattr(cell, "tables", ()):
                    nested_tables.append(sub_tbl)
            row_cells.append(cell.text.strip())
        if any(row_cells):
            grid.append(row_cells)

    if grid:
        yield grid

    for sub in nested_tables:
        yield from _extract_docx_table_grids(sub)


def parse_docx(
    source: str | Path | bytes,
    *,
    source_name: str = "docx",
    extract_images: bool = True,
) -> ContentAST:
    """Parse a `.docx` file path or byte buffer into a `ContentAST`.

    Fault-tolerant: returns an empty `ContentAST` if the input is corrupted
    or not a valid OpenXML Word archive.
    """
    try:
        import docx  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("python-docx is not installed; skipping DOCX parse")
        return ContentAST(nodes=())

    try:
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.is_file():
                logger.warning("DOCX file not found: %s", path)
                return ContentAST(nodes=())
            doc = docx.Document(str(path))
        elif isinstance(source, (bytes, bytearray, memoryview)):
            raw = bytes(source)
            if not raw:
                return ContentAST(nodes=())
            doc = docx.Document(io.BytesIO(raw))
        else:
            return ContentAST(nodes=())
    except Exception:
        logger.warning("Invalid or corrupted DOCX archive at %s", source_name)
        return ContentAST(nodes=())

    nodes: list[Node] = []
    para_idx = 0
    table_idx = 0

    for kind, item in _iter_docx_blocks(doc):
        if kind == "p":
            txt = item.text.strip()
            if txt:
                nodes.append(TextNode.from_text(txt, path=f"{source_name}/p[{para_idx}]"))
                para_idx += 1
        elif kind == "tbl":
            for raw_grid in _extract_docx_table_grids(item):
                tbl_ast = TableGrid.from_raw_grid(
                    raw_grid, source=f"{source_name}/table[{table_idx}]"
                ).to_ast()
                nodes.extend(tbl_ast.nodes)
                table_idx += 1

    if extract_images and hasattr(doc, "part") and hasattr(doc.part, "rels"):
        _DOCX_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        for rel in doc.part.rels.values():
            target_ref = str(getattr(rel, "target_ref", ""))
            if "image" not in target_ref.lower():
                continue
            try:
                blob: bytes = rel.target_part.blob
                with Image.open(io.BytesIO(blob)) as im:
                    im.verify()
                digest = hashlib.sha256(blob).hexdigest()[:12]
                ext = Path(target_ref).suffix.lower() or ".png"
                media_file = _DOCX_MEDIA_DIR / f"{digest}_{Path(target_ref).stem}{ext}"
                if not media_file.is_file():
                    media_file.write_bytes(blob)
                img_ast = parse_banner_image(
                    media_file,
                    path=str(media_file),
                    alt=None,
                )
                nodes.extend(img_ast.nodes)
            except (AttributeError, UnidentifiedImageError, OSError, ValueError):
                continue

    return ContentAST(nodes=tuple(nodes))
