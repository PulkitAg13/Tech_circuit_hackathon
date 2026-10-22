"""ContentAST: the unified, immutable representation of a content bundle.

Parsers produce it; checks consume it. Every node is identified by a content hash,
so unchanged paragraphs keep their identity across edits.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from canongate.domain.types import NodeId, content_hash, text_node_id


class NodeKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"


class TextNode(BaseModel, frozen=True):
    """A block of text in the content bundle (paragraph, heading, list item, etc.)."""

    kind: Literal[NodeKind.TEXT] = NodeKind.TEXT
    id: NodeId
    text: str
    path: str  # e.g. "body/p[3]" — where in the document this came from

    @classmethod
    def from_text(cls, text: str, path: str = "") -> TextNode:
        return cls(id=text_node_id(text), text=text, path=path)


class ImageNode(BaseModel, frozen=True):
    """An image asset in the content bundle."""

    kind: Literal[NodeKind.IMAGE] = NodeKind.IMAGE
    id: NodeId
    asset_path: str  # local path or URI to the image file
    width: int
    height: int
    alt: str | None = None

    @classmethod
    def from_bytes(
        cls, data: bytes, *, path: str, width: int, height: int, alt: str | None = None
    ) -> ImageNode:
        return cls(
            id=NodeId(content_hash(data)),
            asset_path=path,
            width=width,
            height=height,
            alt=alt,
        )


Node = Annotated[TextNode | ImageNode, Field(discriminator="kind")]


class ContentAST(BaseModel, frozen=True):
    """Immutable sequence of content nodes. This is what checks receive."""

    nodes: tuple[Node, ...]

    def __iter__(self) -> Iterator[Node]:  # type: ignore[override]
        return iter(self.nodes)

    def __len__(self) -> int:
        return len(self.nodes)

    def __getitem__(self, idx: int) -> Node:
        return self.nodes[idx]

    def of_kind(self, kind: NodeKind) -> Iterator[Node]:
        """Yield only nodes matching the given kind."""
        return (n for n in self.nodes if n.kind == kind)

    @classmethod
    def from_texts(cls, texts: list[str]) -> ContentAST:
        """Convenience: build an AST from a list of plain strings."""
        nodes = tuple(TextNode.from_text(t, path=f"p[{i}]") for i, t in enumerate(texts))
        return cls(nodes=nodes)
