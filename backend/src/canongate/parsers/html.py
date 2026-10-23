"""HTML DOM, Table, Image Alt-Text, and CSS Hidden-Text Parser (`parsers/html.py`).

Uses `BeautifulSoup` (`html.parser`) to convert campaign HTML pages or email
templates into a `ContentAST`:
1. Strips non-visible code blocks (`script`, `style`, `noscript`, `template`).
2. Detects elements hidden via inline CSS (`display: none`, `visibility: hidden`,
   `opacity: 0`, `font-size: 0`, or identical foreground/background colour) and
   tags their path as `{source}/hidden[{i}]` to expose OWASP LLM01 prompt injection.
3. Linearizes HTML `table` elements via `TableGrid` (preserving `colspan` and
   `th`/`td` headers).
4. Extracts `img` elements as `ImageNode`s (preserving `alt` attributes for
   WCAG 2.1 AA alt-text auditing).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from canongate.domain.ast import ContentAST, ImageNode, Node, TextNode
from canongate.parsers.banner import parse_banner_image as parse_image
from canongate.parsers.tables import TableGrid

logger = logging.getLogger(__name__)

_STRIP_TAGS = ("script", "style", "noscript", "template", "svg", "head")
_TEXT_BLOCK_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "figcaption")
_HIDDEN_STYLE_RE = re.compile(
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?(?:\s*;|\s*$)|"
    r"font-size\s*:\s*0(?:px|pt|em|rem|%)?)",
    re.IGNORECASE,
)
_COLOR_PROP_RE = re.compile(
    r"(?:^|;)\s*(color|background-color|background)\s*:\s*([^;]+)",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")


def _is_element_hidden(tag: Tag) -> bool:
    """Return True if `tag` or any ancestor carries hidden attributes or zero-visibility CSS."""
    curr: Tag | None = tag
    while curr is not None and isinstance(curr, Tag):
        if curr.has_attr("hidden") or str(curr.get("aria-hidden", "")).lower() == "true":
            return True
        style = str(curr.get("style", ""))
        if style:
            if _HIDDEN_STYLE_RE.search(style):
                return True
            props = {
                m.group(1).lower(): m.group(2).strip().lower()
                for m in _COLOR_PROP_RE.finditer(style)
            }
            fg = props.get("color")
            bg = props.get("background-color") or props.get("background")
            if fg and bg and fg == bg:
                return True
        curr = curr.parent if isinstance(curr.parent, Tag) else None
    return False


def _extract_html_table_grid(table_tag: Tag) -> list[list[str]]:
    grid: list[list[str]] = []
    for tr in table_tag.find_all("tr"):
        row: list[str] = []
        for cell in tr.find_all(("th", "td"), recursive=False):
            text = _WS_RE.sub(" ", cell.get_text(" ", strip=True)).strip()
            try:
                colspan = max(1, int(cell.get("colspan", 1)))
            except (ValueError, TypeError):
                colspan = 1
            row.extend([text] * colspan)
        if any(row):
            grid.append(row)
    return grid


def parse_html(
    raw_html: str | bytes | Path,
    *,
    source: str = "html",
    base_dir: Path | None = None,
) -> ContentAST:
    """Parse an HTML string, byte buffer, or file into a `ContentAST`."""
    try:
        if isinstance(raw_html, Path):
            if not raw_html.is_file():
                return ContentAST(nodes=())
            base_dir = base_dir or raw_html.parent
            html_str = raw_html.read_text(encoding="utf-8", errors="replace")
        elif isinstance(raw_html, (bytes, bytearray)):
            html_str = bytes(raw_html).decode("utf-8", errors="replace")
        else:
            html_str = str(raw_html)
    except OSError:
        logger.warning("Failed to read HTML source at %s", source)
        return ContentAST(nodes=())

    if not html_str.strip():
        return ContentAST(nodes=())

    soup = BeautifulSoup(html_str, "html.parser")
    for junk in soup.find_all(_STRIP_TAGS):
        junk.decompose()

    nodes: list[Node] = []
    hidden_idx = 0
    table_idx = 0
    block_idx = 0
    img_idx = 0

    # 1. Extract hidden text elements first (even on generic span/div tags)
    for elem in soup.find_all(True):
        if not isinstance(elem, Tag):
            continue
        if _is_element_hidden(elem):
            # Only emit leaf-most hidden containers to avoid parent/child duplication
            has_hidden_child = any(
                isinstance(c, Tag) and _is_element_hidden(c) for c in elem.find_all(True)
            )
            if not has_hidden_child:
                txt = _WS_RE.sub(" ", elem.get_text(" ", strip=True)).strip()
                if txt:
                    nodes.append(TextNode.from_text(txt, path=f"{source}/hidden[{hidden_idx}]"))
                    hidden_idx += 1
                elem.decompose()

    # 2. Extract and linearize tables (removing them from DOM so cells are not re-emitted)
    for tbl in soup.find_all("table"):
        raw_grid = _extract_html_table_grid(tbl)
        tbl_ast = TableGrid.from_raw_grid(
            raw_grid, source=f"{source}/table[{table_idx}]"
        ).to_ast()
        nodes.extend(tbl_ast.nodes)
        table_idx += 1
        tbl.decompose()

    # 3. Extract images (with alt-text preservation)
    for img in soup.find_all("img"):
        src = str(img.get("src", "")).strip()
        alt_val = img.get("alt")
        alt_str = str(alt_val).strip() if alt_val is not None else None

        if base_dir is not None and src and not src.startswith(("http://", "https://", "data:")):
            candidate = (base_dir / src).resolve()
            if candidate.is_file():
                img_ast = parse_image(
                    candidate,
                    path=f"{source}/img[{img_idx}]",
                    alt=alt_str,
                )
                nodes.extend(img_ast.nodes)
                img_idx += 1
                continue

        try:
            w = max(1, int(img.get("width", 100)))
            h = max(1, int(img.get("height", 100)))
        except (ValueError, TypeError):
            w, h = 100, 100
        nodes.append(
            ImageNode.from_bytes(
                (src or f"img-{img_idx}").encode("utf-8"),
                path=src or f"{source}/img[{img_idx}]",
                width=w,
                height=h,
                alt=alt_str,
            )
        )
        img_idx += 1

    # 4. Extract semantic text blocks in document order
    for blk in soup.find_all(_TEXT_BLOCK_TAGS):
        # Skip if nested inside another semantic text block
        if any(p.name in _TEXT_BLOCK_TAGS for p in blk.parents if isinstance(p, Tag)):
            continue
        txt = _WS_RE.sub(" ", blk.get_text(" ", strip=True)).strip()
        if txt:
            nodes.append(TextNode.from_text(txt, path=f"{source}/{blk.name}[{block_idx}]"))
            block_idx += 1

    # Fallback: if HTML had raw text without semantic block tags
    if block_idx == 0 and table_idx == 0:
        fallback_txt = _WS_RE.sub(" ", soup.get_text(" ", strip=True)).strip()
        if fallback_txt:
            nodes.append(TextNode.from_text(fallback_txt, path=f"{source}/p[0]"))

    return ContentAST(nodes=tuple(nodes))
