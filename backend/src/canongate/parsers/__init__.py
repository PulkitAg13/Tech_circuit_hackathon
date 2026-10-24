"""Multimodal content parsers producing immutable `ContentAST` instances."""

from canongate.parsers.banner import (
    BannerOCREngine,
    OCRBox,
    default_ocr_engine,
    detect_banner_text_boxes,
    parse_banner_image,
)
from canongate.parsers.bundle import (
    BundleInput,
    BundleParser,
    default_bundle_parser,
    parse_bundle,
)
from canongate.parsers.docx import parse_docx
from canongate.parsers.html import parse_html
from canongate.parsers.image import parse_image, parse_image_ast
from canongate.parsers.llm_table import (
    LLMProviderConfig,
    MultiProviderJsonLLM,
    create_llm_canon_extractor,
    denormalize_table_with_llm,
    is_complex_table,
    verify_and_repair_llm_row,
)
from canongate.parsers.pdf import parse_pdf
from canongate.parsers.tables import TableGrid, is_footnote_text, parse_markdown_text
from canongate.parsers.text import parse_text

__all__ = [
    "BannerOCREngine",
    "BundleInput",
    "BundleParser",
    "LLMProviderConfig",
    "MultiProviderJsonLLM",
    "OCRBox",
    "TableGrid",
    "create_llm_canon_extractor",
    "default_bundle_parser",
    "default_ocr_engine",
    "denormalize_table_with_llm",
    "detect_banner_text_boxes",
    "is_complex_table",
    "is_footnote_text",
    "parse_banner_image",
    "parse_bundle",
    "parse_docx",
    "parse_html",
    "parse_image",
    "parse_image_ast",
    "parse_markdown_text",
    "parse_pdf",
    "parse_text",
    "verify_and_repair_llm_row",
]
