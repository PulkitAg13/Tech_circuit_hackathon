"""Context-aware 2D table grid normalization, hierarchical header merging,
and guarded LLM linearization.

Handles the 5 complex tabular structures common in Indian BFSI (RBI Key Fact Statements)
and D2C (ASCI/CCPA) compliance documents:
1. **Multi-Level Hierarchical Headers:** Detects 2- or 3-row spanned header hierarchies
   (e.g., Row 0 `Interest Rate (p.a.)` spanning Row 1 `Salaried | Self-Employed`) and
   merges them into `Interest Rate (p.a.) › Salaried`.
2. **2-Column Key-Value Infoboxes / KFS Grids:** Recognizes 2-column `[Label, Value]`
   tables where Row 0 Col 1 already contains numeric/currency/date anchors so Row 0 is
   preserved as data (`Maximum Loan Amount: Up to Rs 50,000`) instead of consumed as headers.
3. **Vertical `rowspan` Category Stubs:** Forward-fills empty Column 0 category cells
   across vertically merged product groups.
4. **Symbol-Keyed & External Post-Table Footnotes:** Binds symbol-specific footnotes
   (`*`, `†`, `‡`, `§`, `[1]`) to matching rows (or table-wide when unreferenced) and
   attaches footnote paragraphs placed immediately below a table.
5. **Guarded Multi-Provider LLM De-Normalization (`llm_table.py`):** When a table is
   structurally complex and an LLM provider (`Gemini` free API key, `OpenAI`/`Groq`, or
   local `Ollama`) is configured, de-normalizes rows into self-contained propositions
   behind Guard 1 (zero hallucinated numbers + 100% value-anchor recall).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from canongate.domain.ast import ContentAST, Node, TextNode
from canongate.parsers.banner import parse_banner_image
from canongate.parsers.llm_table import (
    MultiProviderJsonLLM,
    denormalize_table_with_llm,
    extract_table_anchors,
    is_complex_table,
)

_WS_COLLAPSE = re.compile(r"\s+")
_MD_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
_FOOTNOTE_PREFIX = re.compile(
    r"^(?:[\*\†\‡\§\#]+|\[\d+\]|note\b|disclaimer\b|t&c\b|terms\b)",
    re.IGNORECASE,
)
_SYMBOL_MARKER_RE = re.compile(r"^([\*\†\‡\§]+|\[\d+\])")


def _clean_cell(val: object) -> str:
    if val is None:
        return ""
    return _WS_COLLAPSE.sub(" ", str(val)).strip()


def _is_markdown_separator_row(row: Sequence[str]) -> bool:
    non_empty = [c for c in row if c]
    return bool(non_empty) and all(_MD_SEPARATOR_CELL.match(c) for c in non_empty)


def is_footnote_text(text: str) -> bool:
    """Return True if a standalone text line or paragraph is a table footnote/disclaimer."""
    cleaned = _clean_cell(text)
    return bool(cleaned and _FOOTNOTE_PREFIX.match(cleaned))


def _is_footnote_row(row: Sequence[str]) -> bool:
    non_empty = [c for c in row if c]
    if not non_empty:
        return False
    unique_vals = set(non_empty)
    if len(unique_vals) == 1:
        text = next(iter(unique_vals))
        if _FOOTNOTE_PREFIX.match(text):
            return True
    return len(non_empty) == 1 and bool(_FOOTNOTE_PREFIX.match(non_empty[0]))


def _is_key_value_two_col_grid(rows: Sequence[Sequence[str]]) -> bool:
    """Detect 2-column `[Field, Value]` KFS tables where Row 0 Col 1 already has a value anchor."""
    if len(rows) < 2 or any(len(r) != 2 for r in rows):
        return False
    r0_key, r0_val = rows[0][0], rows[0][1]
    if not r0_key or not r0_val:
        return False
    # In a Key-Value table, Col 0 is a label without numbers
    # and Col 1 has a numeric/currency/date anchor
    if extract_table_anchors(r0_key):
        return False
    if not extract_table_anchors(r0_val):
        return False
    return any(extract_table_anchors(r[1]) for r in rows[1:] if len(r) == 2 and r[1])


def _is_subheader_row(
    parent_row: Sequence[str],
    candidate_row: Sequence[str],
    remaining_rows: Sequence[Sequence[str]],
) -> bool:
    """Return True if `candidate_row` is a hierarchical sub-header row under `parent_row`."""
    if not remaining_rows:
        return False
    # Sub-header rows contain category labels (no numeric/currency/percentage/date value anchors)
    if any(extract_table_anchors(c) for c in candidate_row if c):
        return False
    # Parent row must have horizontal spans (empty cell or repeated adjacent colspan text)
    parent_has_span = any(c == "" for c in parent_row) or any(
        parent_row[i] and parent_row[i] == parent_row[i - 1] for i in range(1, len(parent_row))
    )
    if not parent_has_span:
        return False
    # At least one subsequent data row must contain value anchors or substantive values
    return any(
        any(extract_table_anchors(c) for c in r if c)
        for r in remaining_rows
        if not _is_footnote_row(r)
    )


def _merge_header_rows(header_rows: Sequence[Sequence[str]], max_cols: int) -> list[str]:
    """Merge 1..K header rows into hierarchical `Parent › Subheader` column names."""
    if len(header_rows) == 1:
        raw_headers = header_rows[0]
        headers: list[str] = []
        last_header = ""
        for idx, h in enumerate(raw_headers):
            if h:
                if h == last_header and idx > 0:
                    headers.append(f"{last_header} ({idx + 1})")
                else:
                    last_header = h
                    headers.append(h)
            elif last_header:
                headers.append(f"{last_header} ({idx + 1})")
            else:
                headers.append(f"Col {idx + 1}")
        return headers

    # Multi-row hierarchical merge: forward-fill parent rows across horizontal spans
    filled_levels: list[list[str]] = []
    for level_idx, h_row in enumerate(header_rows):
        filled: list[str] = []
        last_val = ""
        for _col_idx, cell in enumerate(h_row):
            if cell:
                last_val = cell
                filled.append(cell)
            elif level_idx < len(header_rows) - 1 and last_val:
                # Forward-fill parent super-header across spanned child columns
                filled.append(last_val)
            else:
                filled.append("")
        filled_levels.append(filled)

    merged: list[str] = []
    for col_idx in range(max_cols):
        parts: list[str] = []
        for level in filled_levels:
            val = level[col_idx] if col_idx < len(level) else ""
            if val and (not parts or parts[-1].lower() != val.lower()):
                parts.append(val)
        if parts:
            merged.append(" › ".join(parts))
        else:
            merged.append(f"Col {col_idx + 1}")
    return merged


def _select_footnotes_for_row(
    row: Sequence[str],
    all_rows: Sequence[Sequence[str]],
    footnotes: Sequence[str],
) -> tuple[str, ...]:
    """Bind symbol-keyed footnotes (`*`, `†`, `‡`, `[1]`) to matching rows,
    or all rows if unkeyed.
    """
    if not footnotes:
        return ()
    row_joined = " ".join(c for c in row if c)
    all_joined = " ".join(c for r in all_rows for c in r if c)

    selected: list[str] = []
    for fn in footnotes:
        m = _SYMBOL_MARKER_RE.match(fn.strip())
        if m:
            sym = m.group(1)
            # If the symbol explicitly appears inside at least one data cell in the table,
            # attach this footnote only to rows carrying that symbol.
            if sym in all_joined:
                if sym in row_joined:
                    selected.append(fn)
                continue
        selected.append(fn)
    return tuple(selected)


@dataclass(frozen=True, slots=True)
class TableGrid:
    """Immutable, normalized 2D table with header-contextualized row linearization."""

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    footnotes: tuple[str, ...] = ()
    source: str = "table"
    is_key_value: bool = False
    linearized_override: tuple[str, ...] = ()

    @classmethod
    def from_raw_grid(
        cls,
        grid: Sequence[Sequence[object]],
        *,
        source: str = "table",
        extra_footnotes: Sequence[str] = (),
        llm_client: MultiProviderJsonLLM | None = None,
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

        for ext_fn in extra_footnotes:
            cleaned_fn = _clean_cell(ext_fn)
            if cleaned_fn and cleaned_fn not in footnotes:
                footnotes.append(cleaned_fn)

        # Case A: 2-Column Key-Value Infobox / KFS Grid
        if _is_key_value_two_col_grid(cleaned_rows):
            kv_rows: list[tuple[str, ...]] = []
            for row in cleaned_rows:
                if _is_footnote_row(row):
                    fn_text = next(c for c in row if c)
                    if fn_text not in footnotes:
                        footnotes.append(fn_text)
                    continue
                kv_rows.append(tuple(row))
            base_kv = cls(
                headers=("Field", "Value"),
                rows=tuple(kv_rows),
                footnotes=tuple(footnotes),
                source=source,
                is_key_value=True,
            )
            return base_kv._with_optional_llm(grid, llm_client=llm_client)

        # Case B: Detect 1-row vs Multi-Row Hierarchical Headers
        header_rows: list[list[str]] = [cleaned_rows[0]]
        cursor = 1
        while cursor < len(cleaned_rows) - 1 and len(header_rows) < 3:
            if _is_subheader_row(header_rows[-1], cleaned_rows[cursor], cleaned_rows[cursor + 1 :]):
                header_rows.append(cleaned_rows[cursor])
                cursor += 1
            else:
                break

        headers = _merge_header_rows(header_rows, max_cols)

        # Extract data rows & forward-fill vertical rowspan stubs in Column 0
        data_rows: list[tuple[str, ...]] = []
        prev_col0_stub = ""
        for row in cleaned_rows[cursor:]:
            if _is_footnote_row(row):
                fn_text = next(c for c in row if c)
                if fn_text not in footnotes:
                    footnotes.append(fn_text)
                continue
            row_mut = list(row)
            if max_cols >= 2:
                if row_mut[0]:
                    prev_col0_stub = row_mut[0]
                elif prev_col0_stub and any(row_mut[1:]):
                    row_mut[0] = prev_col0_stub
            data_rows.append(tuple(row_mut))

        # If table had only 1 row total, treat it as a single data row with generic headers
        if not data_rows and cleaned_rows:
            generic_headers = tuple(f"Col {i + 1}" for i in range(max_cols))
            return cls(
                headers=generic_headers,
                rows=(tuple(cleaned_rows[0]),),
                footnotes=tuple(footnotes),
                source=source,
            )

        base_grid = cls(
            headers=tuple(headers),
            rows=tuple(data_rows),
            footnotes=tuple(footnotes),
            source=source,
        )
        return base_grid._with_optional_llm(grid, llm_client=llm_client)

    def _with_optional_llm(
        self,
        raw_grid: Sequence[Sequence[object]],
        *,
        llm_client: MultiProviderJsonLLM | None = None,
    ) -> TableGrid:
        """If table is complex and an LLM provider is active, run guarded LLM de-normalization."""
        client = llm_client or MultiProviderJsonLLM()
        if not client.is_enabled or not self.rows:
            return self
        if llm_client is None and not is_complex_table(raw_grid):
            return self

        det_rows = tuple(self._format_deterministic_row(i) for i in range(len(self.rows)))
        row_fns = tuple(
            _select_footnotes_for_row(self.rows[i], self.rows, self.footnotes)
            for i in range(len(self.rows))
        )
        llm_rows = denormalize_table_with_llm(
            headers=self.headers,
            rows=self.rows,
            footnotes=self.footnotes,
            deterministic_rows=det_rows,
            row_footnotes=row_fns,
            llm_client=client,
        )
        return TableGrid(
            headers=self.headers,
            rows=self.rows,
            footnotes=self.footnotes,
            source=self.source,
            is_key_value=self.is_key_value,
            linearized_override=llm_rows,
        )

    def __len__(self) -> int:
        return len(self.rows)

    def __bool__(self) -> bool:
        return len(self.rows) > 0

    def __iter__(self) -> Iterator[str]:
        for idx in range(len(self.rows)):
            yield self[idx]

    def _format_deterministic_row(self, idx: int) -> str:
        row = self.rows[idx]
        applicable_fns = _select_footnotes_for_row(row, self.rows, self.footnotes)

        if self.is_key_value and len(row) == 2:
            k, v = row[0], row[1]
            line = f"{k}: {v}" if k and v else (k or v)
            if applicable_fns and line:
                line = f"{line} | Footnote: {'; '.join(applicable_fns)}"
            return line

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
        if applicable_fns and line:
            fn_joined = "; ".join(applicable_fns)
            line = f"{line} | Footnote: {fn_joined}"
        return line

    def __getitem__(self, idx: int) -> str:
        if self.linearized_override and 0 <= idx < len(self.linearized_override):
            return self.linearized_override[idx]
        return self._format_deterministic_row(idx)

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


def _parse_markdown_table(
    block: str,
    *,
    source: str,
    extra_footnotes: Sequence[str] = (),
    llm_client: MultiProviderJsonLLM | None = None,
) -> ContentAST:
    raw_grid: list[list[str]] = []
    trailing_fns: list[str] = list(extra_footnotes)
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "|" not in stripped:
            if is_footnote_text(stripped):
                trailing_fns.append(stripped)
            continue
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        raw_grid.append([cell.strip() for cell in stripped.split("|")])
    return TableGrid.from_raw_grid(
        raw_grid,
        source=source,
        extra_footnotes=trailing_fns,
        llm_client=llm_client,
    ).to_ast()


def parse_markdown_text(
    raw: str,
    *,
    source: str = "text",
    base_dir: Path | None = None,
    llm_client: MultiProviderJsonLLM | None = None,
) -> ContentAST:
    """Parse raw text or Markdown (including pipe tables and local images) into a ContentAST."""
    if not raw or not raw.strip():
        return ContentAST(nodes=())

    blocks = [b.strip() for b in _BLOCK_SPLIT.split(raw.strip()) if b.strip()]
    nodes: list[Node] = []
    para_idx = 0
    table_idx = 0
    idx = 0

    while idx < len(blocks):
        cleaned = blocks[idx]
        if _is_markdown_table_block(cleaned):
            # Look ahead: if the immediately following paragraph block is a standalone footnote
            # (`*T&C...`, `†Valid...`, `Note:...`), attach it to this table's footnotes!
            attached_fns: list[str] = []
            while idx + 1 < len(blocks) and not _is_markdown_table_block(blocks[idx + 1]):
                next_blk = blocks[idx + 1]
                next_lines = [ln.strip() for ln in next_blk.splitlines() if ln.strip()]
                if next_lines and all(is_footnote_text(ln) for ln in next_lines):
                    attached_fns.extend(next_lines)
                    idx += 1
                else:
                    break

            tbl_ast = _parse_markdown_table(
                cleaned,
                source=f"{source}/table[{table_idx}]",
                extra_footnotes=attached_fns,
                llm_client=llm_client,
            )
            nodes.extend(tbl_ast.nodes)
            table_idx += 1
            idx += 1
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
        idx += 1

    return ContentAST(nodes=tuple(nodes))
