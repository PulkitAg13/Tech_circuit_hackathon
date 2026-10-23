"""Unified Multimodal Campaign Bundle Dispatcher (`parsers/bundle.py`).

Routes any combination of plain text, Markdown, HTML, DOCX, PDF, and raster
banner images (`.png`, `.jpg`, `.jpeg`, `.webp`) into a single immutable
`ContentAST` via `ContentAST.__add__`.

Fault isolation:
Each attachment in a bundle is parsed inside an isolated guard so a single
corrupted attachment never aborts parsing the remaining campaign assets.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from canongate.domain.ast import ContentAST
from canongate.parsers.docx import parse_docx
from canongate.parsers.html import parse_html
from canongate.parsers.banner import parse_banner_image as parse_image
from canongate.parsers.pdf import parse_pdf
from canongate.parsers.tables import parse_markdown_text as parse_text

logger = logging.getLogger(__name__)

BundleInput = str | Path | tuple[str, bytes | str]


class BundleParser:
    """Callable, extensible dispatcher that routes files or buffers to format parsers."""

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., ContentAST]] = {
            ".txt": self._parse_text_file,
            ".md": self._parse_text_file,
            ".markdown": self._parse_text_file,
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
                payload.decode("utf-8", errors="replace")
                if isinstance(payload, bytes)
                else payload
            )
            return parse_text(text, source=stem)
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
