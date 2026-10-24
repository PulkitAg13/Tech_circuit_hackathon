"""Plain-text and Markdown parser → ContentAST.

Splits on blank lines to get paragraphs and delegates Markdown image tags
`![alt](path)` and `image_paths` to `parse_banner_image` so embedded banners
automatically produce both `ImageNode`s and OCR `TextNode`s.
"""

from __future__ import annotations

import re
from pathlib import Path

from canongate.domain.ast import ContentAST, Node, TextNode
from canongate.parsers.banner import parse_banner_image

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
    pointing to valid image files is converted into `ImageNode`s + OCR `TextNode`s
    via `parse_banner_image`.
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
                img_ast = parse_banner_image(p, path=str(p), alt=alt or None)
                if img_ast.nodes:
                    nodes.extend(img_ast.nodes)
                    continue
        nodes.append(TextNode.from_text(b, path=f"{source}/p[{i}]"))

    if image_paths:
        for p_str in image_paths:
            p = Path(p_str)
            if p.is_file():
                img_ast = parse_banner_image(p, path=str(p))
                nodes.extend(img_ast.nodes)

    return ContentAST(nodes=tuple(nodes))
