"""Image parser → ContentAST with ImageNode.

Extracts image metadata and bytes into a deterministic, frozen ImageNode.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from canongate.domain.ast import ContentAST, ImageNode


def parse_image(file_path: str | Path, *, alt: str | None = None) -> ImageNode:
    """Parse a local image asset into a domain ImageNode."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Image asset not found at {p}")

    data = p.read_bytes()
    with Image.open(p) as img:
        width, height = img.size

    return ImageNode.from_bytes(data, path=str(p), width=width, height=height, alt=alt)


def parse_image_ast(file_path: str | Path, *, alt: str | None = None) -> ContentAST:
    """Convenience: parse an image file into a single-node ContentAST."""
    node = parse_image(file_path, alt=alt)
    return ContentAST(nodes=(node,))
