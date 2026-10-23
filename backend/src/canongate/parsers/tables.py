"""Context-aware 2D table grid normalization and deterministic row linearization.

Why this exists:
Financial Key Fact Statements (KFS), pricing grids, and nutraceutical ingredient
tables rely on column headers, merged cells, and trailing footnote qualifiers
(`*T&C Apply`, `†Valid until 30 Sept 2026`). Emitting bare cell text (`"0%"`)
loses the subject/condition relationship, while using an unguarded LLM at scan
time risks numeric hallucination and destroys character offsets.

`TableGrid` normalizes raw 2D cell arrays from `pdfplumber`, `python-docx`,
HTML DOMs, or Markdown pipe tables:
1. Forward-fills horizontal spanned header cells (`None` / `""`).
2. Separates trailing footnote/disclaimer rows (`*`, `†`, `‡`, `Note:`, `T&C`)
   and attaches them as table-level qualifiers.
3. Linearizes each data row into a self-contained `TextNode` (`{Header}: {Value}`)
   so Tier 1, Tier 1.5 (algebra), and Tier 2 (NLI + SlotDiff) checks can verify
   tabular claims deterministically.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from canongate.domain.ast import ContentAST, Node, TextNode
from canongate.parsers.banner import parse_banner_image

_WS_COLLAPSE = re.compile(r"\s+")
_MD_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
_FOOTNOTE_PREFIX = re.compile(
    r"^(?:[\*\†\‡\§\#]+|\[\d+\]|note\b|disclaimer\b|t&c\b|terms\b)",
    re.IGNORECASE,
)


def _clean_cell(val: object) -> str:
    if val is None:
        return ""
    return _WS_COLLAPSE.sub(" ", str(val)).strip()


def _is_markdown_separator_row(row: Sequence[str]) -> bool:
    non_empty = [c for c in row if c]
    return bool(non_empty) and all(_MD_SEPARATOR_CELL.match(c) for c in non_empty)


def _is_footnote_row(row: Sequence[str]) -> bool:
    non_empty = [c for c in row if c]
    if not non_empty:
        return False
    # Single unique text across the row (or single non-empty cell) starting with a footnote marker
    unique_vals = set(non_empty)
    if len(unique_vals) == 1:
        text = next(iter(unique_vals))
        if _FOOTNOTE_PREFIX.match(text):
            return True
    return len(non_empty) == 1 and bool(_FOOTNOTE_PREFIX.match(non_empty[0]))


@dataclass(frozen=True, slots=True)
class TableGrid:
    """Immutable, normalized 2D table with header-contextualized row linearization."""

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    footnotes: tuple[str, ...] = ()
    source: str = "table"

    @classmethod
    def from_raw_grid(
        cls,
        grid: Sequence[Sequence[object]],
        *,
        source: str = "table",
    ) -> TableGrid:
        """Normalize a raw 2D cell sequence from PDF, DOCX, HTML, or Markdown."""
        cleaned_rows: list[list[str]] = []
        max_cols = 0
        for raw_row in grid:
            row = [_clean_cell(c) for c in raw_row]
            if not any(row) or _is_markdown_separator_row(row):
                continue
            cleaned_rows.append(row)
            if len(row) > max_cols:
                max_cols = len(row)

        if not cleaned_rows or max_cols == 0:
            return cls(headers=(), rows=(), footnotes=(), source=source)

        # Pad rows to uniform width
        for row in cleaned_rows:
            if len(row) < max_cols:
                row.extend([""] * (max_cols - len(row)))

        # Extract trailing footnote rows from the bottom of the table
        footnotes: list[str] = []
        while len(cleaned_rows) > 1 and _is_footnote_row(cleaned_rows[-1]):
            fn_row = cleaned_rows.pop()
            fn_text = next(c for c in fn_row if c)
            if fn_text not in footnotes:
                footnotes.insert(0, fn_text)

        # Forward-fill spanned/empty header cells in the first row
        raw_headers = cleaned_rows[0]
        headers: list[str] = []
        last_header = ""
        for idx, h in enumerate(raw_headers):
            if h:
                last_header = h
                headers.append(h)
            elif last_header:
                headers.append(f"{last_header} ({idx + 1})")
            else:
                headers.append(f"Col {idx + 1}")

        data_rows: list[tuple[str, ...]] = []
        for row in cleaned_rows[1:]:
            if _is_footnote_row(row):
                fn_text = next(c for c in row if c)
                if fn_text not in footnotes:
                    footnotes.append(fn_text)
                continue
            # Deduplicate identical adjacent cells produced by horizontal colspan in DOCX/PDF
            data_rows.append(tuple(row))

        # If table had only 1 row total, treat it as a single data row with generic headers
        if not data_rows and cleaned_rows:
            generic_headers = tuple(f"Col {i + 1}" for i in range(max_cols))
            return cls(
                headers=generic_headers,
                rows=(tuple(cleaned_rows[0]),),
                footnotes=tuple(footnotes),
                source=source,
            )

        return cls(
            headers=tuple(headers),
            rows=tuple(data_rows),
            footnotes=tuple(footnotes),
            source=source,
        )

    def __len__(self) -> int:
        return len(self.rows)

    def __bool__(self) -> bool:
        return len(self.rows) > 0

    def __iter__(self) -> Iterator[str]:
        for idx in range(len(self.rows)):
            yield self[idx]

    def __getitem__(self, idx: int) -> str:
        row = self.rows[idx]
        pairs: list[str] = []
        seen_pairs: set[tuple[str, str]] = set()
        for col_idx, val in enumerate(row):
            if not val:
                continue
            hdr = self.headers[col_idx] if col_idx < len(self.headers) else f"Col {col_idx + 1}"
            pair_key = (hdr, val)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            pairs.append(f"{hdr}: {val}")

        line = " | ".join(pairs)
        if self.footnotes and line:
            fn_joined = "; ".join(self.footnotes)
            line = f"{line} | Footnote: {fn_joined}"
        return line

    def to_ast(self) -> ContentAST:
        """Convert all non-empty linearized rows into a `ContentAST` of `TextNode`s."""
        nodes: list[TextNode] = []
        for idx, line in enumerate(self):
            if line:
                nodes.append(TextNode.from_text(line, path=f"{self.source}/r[{idx}]"))
        return ContentAST(nodes=tuple(nodes))


_BLOCK_SPLIT = re.compile(r"\n{2,}")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\s*\(([^)]+)\)")


def _is_markdown_table_block(block: str) -> bool:
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    return all("|" in ln for ln in lines[:2]) and "-" in lines[1]


def _parse_markdown_table(block: str, *, source: str) -> ContentAST:
    raw_grid: list[list[str]] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or "|" not in stripped:
            continue
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        raw_grid.append([cell.strip() for cell in stripped.split("|")])
    return TableGrid.from_raw_grid(raw_grid, source=source).to_ast()


def parse_markdown_text(
    raw: str,
    *,
    source: str = "text",
    base_dir: Path | None = None,
) -> ContentAST:
    """Parse raw text or Markdown (including pipe tables and local images) into a ContentAST."""
    if not raw or not raw.strip():
        return ContentAST(nodes=())

    blocks = _BLOCK_SPLIT.split(raw.strip())
    nodes: list[Node] = []
    para_idx = 0
    table_idx = 0

    for block in blocks:
        cleaned = block.strip()
        if not cleaned:
            continue

        if _is_markdown_table_block(cleaned):
            tbl_ast = _parse_markdown_table(cleaned, source=f"{source}/table[{table_idx}]")
            nodes.extend(tbl_ast.nodes)
            table_idx += 1
            continue

        nodes.append(TextNode.from_text(cleaned, path=f"{source}/p[{para_idx}]"))
        para_idx += 1

        if base_dir is not None:
            for match in _MD_IMAGE_RE.finditer(cleaned):
                alt_text, rel_path = match.group(1), match.group(2).strip()
                candidate = (base_dir / rel_path).resolve()
                if candidate.is_file():
                    img_ast = parse_banner_image(
                        candidate,
                        path=f"{source}/img[{para_idx - 1}]",
                        alt=alt_text or None,
                    )
                    nodes.extend(img_ast.nodes)

    return ContentAST(nodes=tuple(nodes))
