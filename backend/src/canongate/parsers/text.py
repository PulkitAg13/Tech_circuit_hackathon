"""Plain-text and Markdown parser → ContentAST.

For the walking skeleton, this is intentionally simple:
- Splits on blank lines to get paragraphs
- Each paragraph becomes a TextNode

Later, we can upgrade to a proper Markdown parser (mistune/marko)
that preserves heading levels, lists, etc.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from canongate.domain.ast import ContentAST, ImageNode, Node, TextNode

_BLOCK_SPLIT = re.compile(r"\n{2,}")
_MD_IMAGE = re.compile(r"^!\[(.*?)\]\((.*?)\)$")


def parse_text(
    raw: str,
    *,
    source: str = "text",
    image_paths: list[str] | None = None,
) -> ContentAST:
    """Parse raw text (or markdown) and optional images into a ContentAST.

    Paragraphs are split on double newlines. Markdown image syntax `![alt](path)`
    pointing to valid image files is converted into ImageNodes.
    """
    blocks = _BLOCK_SPLIT.split(raw.strip())
    nodes: list[Node] = []

    for i, block in enumerate(blocks):
        b = block.strip()
        if not b:
            continue
        m = _MD_IMAGE.match(b)
        if m:
            alt, img_path = m.group(1), m.group(2)
            p = Path(img_path)
            if p.is_file():
                try:
                    data = p.read_bytes()
                    with Image.open(p) as img:
                        w, h = img.size
                    nodes.append(
                        ImageNode.from_bytes(data, path=str(p), width=w, height=h, alt=alt or None)
                    )
                    continue
                except Exception:
                    pass
        nodes.append(TextNode.from_text(b, path=f"{source}/p[{i}]"))

    if image_paths:
        for p_str in image_paths:
            p = Path(p_str)
            if p.is_file():
                try:
                    data = p.read_bytes()
                    with Image.open(p) as img:
                        w, h = img.size
                    nodes.append(ImageNode.from_bytes(data, path=str(p), width=w, height=h))
                except Exception:
                    pass

    return ContentAST(nodes=tuple(nodes))
