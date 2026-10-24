"""Image parser utilities (`parsers/image.py`) producing `ImageNode` and `ContentAST`."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from canongate.domain.ast import ContentAST, ImageNode


def parse_image(
    source: str | Path | bytes,
    *,
    path: str | None = None,
    alt: str | None = None,
) -> ImageNode:
    """Parse an image file or byte buffer into a single `ImageNode`."""
    if isinstance(source, (str, Path)):
        file_path = Path(source)
        raw_bytes = file_path.read_bytes()
        asset_path = path if path is not None else str(file_path)
    else:
        raw_bytes = bytes(source)
        asset_path = path if path is not None else "image"

    with Image.open(io.BytesIO(raw_bytes)) as im:
        width, height = im.size

    return ImageNode.from_bytes(
        raw_bytes,
        path=asset_path,
        width=width,
        height=height,
        alt=alt,
    )


def parse_image_ast(
    source: str | Path | bytes,
    *,
    path: str | None = None,
    alt: str | None = None,
) -> ContentAST:
    """Parse an image file or byte buffer into a `ContentAST` containing the `ImageNode`."""
    node = parse_image(source, path=path, alt=alt)
    return ContentAST(nodes=(node,))
