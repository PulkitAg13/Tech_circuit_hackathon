"""Unified Multimodal Campaign & Brand Document Dispatcher (`parsers/bundle.py`).

Routes any combination of plain text, Markdown, CSV, JSON, YAML, HTML, DOCX,
PDF, and raster images (`.png`, `.jpg`, `.jpeg`, `.webp`) into a single
immutable `ContentAST` via `ContentAST.__add__`.

Fault isolation:
Each attachment in a bundle is parsed inside an isolated guard so a single
corrupted attachment never aborts parsing the remaining campaign or brand assets.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml

from canongate.domain.ast import ContentAST
from canongate.parsers.banner import parse_banner_image as parse_image
from canongate.parsers.docx import parse_docx
from canongate.parsers.html import parse_html
from canongate.parsers.pdf import parse_pdf
from canongate.parsers.tables import parse_markdown_text as parse_text

logger = logging.getLogger(__name__)

BundleInput = str | Path | tuple[str, bytes | str]


def _parse_csv_payload(payload: bytes | str, *, source: str) -> ContentAST:
    """Convert CSV rows into structured Markdown table and prose blocks for ContentAST."""
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    reader = csv.reader(io.StringIO(text))
    rows = [[cell.strip() for cell in row] for row in reader if any(c.strip() for c in row)]
    if not rows:
        return ContentAST(nodes=())

    headers = rows[0]
    md_lines: list[str] = []
    if len(rows) >= 2:
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for r in rows[1:]:
            padded = r + [""] * max(0, len(headers) - len(r))
            md_lines.append("| " + " | ".join(padded[: len(headers)]) + " |")

        # Also emit explicit row summaries so Terminology / Fact / Colour rules
        # in CSV columns are extracted
        h_low = [h.lower() for h in headers]
        for r in rows[1:]:
            row_map = {h_low[i]: r[i] for i in range(min(len(h_low), len(r))) if r[i].strip()}
            banned = (
                row_map.get("banned")
                or row_map.get("banned_term")
                or row_map.get("pattern_text")
                or row_map.get("avoid")
            )
            preferred = (
                row_map.get("preferred")
                or row_map.get("preferred_term")
                or row_map.get("replacement")
                or row_map.get("use")
            )
            if banned and preferred:
                md_lines.append(f"\nNever use '{banned}', prefer '{preferred}'.")
            fact_txt = (
                row_map.get("fact")
                or row_map.get("approved_fact")
                or row_map.get("claim")
                or row_map.get("approved_claim")
            )
            if fact_txt:
                cond = row_map.get("condition") or row_map.get("conditions") or ""
                valid = row_map.get("valid_until") or row_map.get("promo_valid_until") or ""
                extra = f" ({cond})" if cond else ""
                v_str = f" valid until {valid}" if valid else ""
                md_lines.append(f"\nApproved Fact: {fact_txt}{extra}{v_str}")
            hex_val = row_map.get("hex") or row_map.get("color") or row_map.get("colour")
            if hex_val and hex_val.startswith("#"):
                c_name = row_map.get("name") or row_map.get("token") or "Brand Color"
                md_lines.append(f"\n{c_name}: {hex_val}")
    else:
        md_lines.append(" | ".join(headers))

    return parse_text("\n".join(md_lines), source=source)


def _flatten_structured_data(data: Any) -> list[str]:
    """Convert arbitrary JSON/YAML company guidelines or fact sheets into canonical text blocks."""
    blocks: list[str] = []
    if isinstance(data, dict):
        # Check for canonical or semi-structured keys
        for t in data.get("terminology") or data.get("terms") or data.get("banned_terms") or ():
            if isinstance(t, dict):
                pat = t.get("pattern_text") or t.get("banned") or t.get("avoid") or t.get("term")
                pref = t.get("preferred") or t.get("use") or t.get("replacement")
                if pat and pref:
                    blocks.append(f"Never use '{pat}', prefer '{pref}'.")
        for c in data.get("palette") or data.get("colors") or data.get("colours") or ():
            if isinstance(c, dict) and c.get("hex"):
                nm = c.get("name") or c.get("id") or "Brand Color"
                blocks.append(f"{nm}: {c['hex']}")
        for f in data.get("facts") or data.get("approved_facts") or data.get("claims") or ():
            if isinstance(f, dict):
                txt = f.get("text") or f.get("claim") or f.get("fact")
                if txt:
                    conds = f.get("conditions") or ()
                    c_str = f" ({'; '.join(str(x) for x in conds)})" if conds else ""
                    vu = f.get("valid_until") or f.get("promo_valid_until")
                    v_str = f" valid until {vu}" if vu else ""
                    blocks.append(f"Approved Fact: {txt}{c_str}{v_str}")
            elif isinstance(f, str) and f.strip():
                blocks.append(f"Approved Fact: {f.strip()}")
        for tr in data.get("trigger_obligations") or data.get("disclaimers") or ():
            if isinstance(tr, dict):
                pat = tr.get("trigger_pattern") or tr.get("trigger")
                disc = tr.get("required_disclaimer_text") or tr.get("disclaimer")
                if pat and disc:
                    blocks.append(f"Trigger: '{pat}' -> Disclaimer: '{disc}'")

        # Generic key-value fallback for arbitrary company JSON objects
        for k, v in data.items():
            if k in (
                "terminology",
                "terms",
                "banned_terms",
                "palette",
                "colors",
                "colours",
                "facts",
                "approved_facts",
                "claims",
                "trigger_obligations",
                "disclaimers",
            ):
                continue
            if isinstance(v, (str, int, float)) and str(v).strip():
                blocks.append(f"{k}: {v}")
            elif isinstance(v, (list, dict)):
                blocks.extend(_flatten_structured_data(v))
    elif isinstance(data, list):
        for item in data:
            blocks.extend(_flatten_structured_data(item))
    elif isinstance(data, (str, int, float)) and str(data).strip():
        blocks.append(str(data).strip())
    return blocks


def _parse_json_or_yaml_payload(
    payload: bytes | str, *, source: str, is_yaml: bool = False
) -> ContentAST:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    try:
        parsed = yaml.safe_load(text) if is_yaml else json.loads(text)
        blocks = _flatten_structured_data(parsed)
        if blocks:
            return parse_text("\n\n".join(blocks), source=source)
    except Exception:
        pass
    return parse_text(text, source=source)


class BundleParser:
    """Callable, extensible dispatcher that routes files or buffers to format parsers."""

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., ContentAST]] = {
            ".txt": self._parse_text_file,
            ".md": self._parse_text_file,
            ".markdown": self._parse_text_file,
            ".csv": self._parse_csv_file,
            ".json": self._parse_json_file,
            ".yaml": self._parse_yaml_file,
            ".yml": self._parse_yaml_file,
            ".html": self._parse_html_file,
            ".htm": self._parse_html_file,
            ".docx": self._parse_docx_file,
            ".pdf": self._parse_pdf_file,
            ".png": self._parse_image_file,
            ".jpg": self._parse_image_file,
            ".jpeg": self._parse_image_file,
            ".webp": self._parse_image_file,
        }

    def register(self, ext: str, handler: Callable[..., ContentAST]) -> None:
        """Register or override a parser for file extension `ext` (e.g. `'.csv'`)."""
        norm = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        self._handlers[norm] = handler

    def __contains__(self, ext: object) -> bool:
        if not isinstance(ext, str):
            return False
        norm = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        return norm in self._handlers

    def __len__(self) -> int:
        return len(self._handlers)

    def __repr__(self) -> str:
        exts = ", ".join(sorted(self._handlers))
        return f"BundleParser(extensions=[{exts}])"

    def parse_one(self, item: BundleInput) -> ContentAST:
        """Parse a single file `Path`, raw text `str`, or `(filename, payload)` tuple."""
        try:
            if isinstance(item, tuple) and len(item) == 2:
                if isinstance(item[0], (bytes, bytearray)) and isinstance(item[1], (str, Path)):
                    payload, filename = item
                    filename = str(filename)
                else:
                    filename, payload = item
                ext = Path(filename).suffix.lower()
                stem = Path(filename).stem or "asset"
                return self._dispatch_payload(ext, stem, filename, payload)

            if isinstance(item, Path):
                ext = item.suffix.lower()
                handler = self._handlers.get(ext)
                if handler is None:
                    logger.warning("Unsupported file extension %r for %s", ext, item)
                    return ContentAST(nodes=())
                return handler(item, source=item.stem or "file")

            if isinstance(item, str):
                # Check if string is an existing file path with a known extension
                if "\n" not in item and len(item) < 4096:
                    candidate = Path(item)
                    if candidate.suffix.lower() in self._handlers and candidate.is_file():
                        return self.parse_one(candidate)
                return parse_text(item, source="text")
        except Exception:
            logger.exception("Fault-isolated parser error on bundle item %r", item)
            return ContentAST(nodes=())

        return ContentAST(nodes=())

    def __call__(self, *items: BundleInput) -> ContentAST:
        """Parse and concatenate multiple bundle inputs into one `ContentAST`."""
        combined = ContentAST(nodes=())
        for item in items:
            combined = combined + self.parse_one(item)
        return combined

    def _dispatch_payload(
        self, ext: str, stem: str, filename: str, payload: bytes | str
    ) -> ContentAST:
        if ext in (".txt", ".md", ".markdown"):
            text = (
                payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
            )
            return parse_text(text, source=stem)
        if ext == ".csv":
            return _parse_csv_payload(payload, source=stem)
        if ext == ".json":
            return _parse_json_or_yaml_payload(payload, source=stem, is_yaml=False)
        if ext in (".yaml", ".yml"):
            return _parse_json_or_yaml_payload(payload, source=stem, is_yaml=True)
        if ext in (".html", ".htm"):
            return parse_html(payload, source=stem)
        if ext == ".docx":
            raw = payload.encode("utf-8") if isinstance(payload, str) else payload
            return parse_docx(raw, source_name=stem)
        if ext == ".pdf":
            raw = payload.encode("utf-8") if isinstance(payload, str) else payload
            return parse_pdf(raw, source_name=stem)
        if ext in (".png", ".jpg", ".jpeg", ".webp"):
            raw = payload.encode("utf-8") if isinstance(payload, str) else payload
            return parse_image(raw, path=filename)
        logger.warning("Unsupported bundle payload extension %r (%s)", ext, filename)
        return ContentAST(nodes=())

    @staticmethod
    def _parse_text_file(path: Path, *, source: str) -> ContentAST:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return parse_text(raw, source=source, base_dir=path.parent)

    @staticmethod
    def _parse_csv_file(path: Path, *, source: str) -> ContentAST:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return _parse_csv_payload(raw, source=source)

    @staticmethod
    def _parse_json_file(path: Path, *, source: str) -> ContentAST:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return _parse_json_or_yaml_payload(raw, source=source, is_yaml=False)

    @staticmethod
    def _parse_yaml_file(path: Path, *, source: str) -> ContentAST:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return _parse_json_or_yaml_payload(raw, source=source, is_yaml=True)

    @staticmethod
    def _parse_html_file(path: Path, *, source: str) -> ContentAST:
        return parse_html(path, source=source, base_dir=path.parent)

    @staticmethod
    def _parse_docx_file(path: Path, *, source: str) -> ContentAST:
        return parse_docx(path, source_name=source)

    @staticmethod
    def _parse_pdf_file(path: Path, *, source: str) -> ContentAST:
        return parse_pdf(path, source_name=source)

    @staticmethod
    def _parse_image_file(path: Path, *, source: str) -> ContentAST:
        return parse_image(path, path=str(path))


default_bundle_parser = BundleParser()


def parse_bundle(*items: BundleInput, items_seq: Sequence[BundleInput] = ()) -> ContentAST:
    """Parse any combination of text, files, or `(filename, bytes)` into a single `ContentAST`."""
    all_items = (*items, *items_seq)
    return default_bundle_parser(*all_items)
