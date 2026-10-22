"""Plain-text and Markdown parser → ContentAST.

For the walking skeleton, this is intentionally simple:
- Splits on blank lines to get paragraphs
- Each paragraph becomes a TextNode

Later, we can upgrade to a proper Markdown parser (mistune/marko)
that preserves heading levels, lists, etc.
"""

from __future__ import annotations

import re

from canongate.domain.ast import ContentAST, TextNode

_BLOCK_SPLIT = re.compile(r"\n{2,}")


def parse_text(raw: str, *, source: str = "text") -> ContentAST:
    """Parse raw text (or markdown) into a ContentAST.

    Paragraphs are split on double newlines. Empty paragraphs are skipped.
    """
    blocks = _BLOCK_SPLIT.split(raw.strip())
    nodes = tuple(
        TextNode.from_text(block.strip(), path=f"{source}/p[{i}]")
        for i, block in enumerate(blocks)
        if block.strip()
    )
    return ContentAST(nodes=nodes)
