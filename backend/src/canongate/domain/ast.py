"""ContentAST: the unified, immutable representation of a content bundle.

Parsers produce it; checks consume it. Every node is identified by a content hash,
so unchanged paragraphs keep their identity across edits.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal, overload

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

    def __len__(self) -> int:
        return len(self.text)

    def __str__(self) -> str:
        return self.text

    def __contains__(self, substring: str) -> bool:
        return substring in self.text


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

    @property
    def path(self) -> str:
        return self.asset_path

    @property
    def dimensions(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height > 0 else 0.0


Node = Annotated[TextNode | ImageNode, Field(discriminator="kind")]


@lru_cache(maxsize=256)
def _build_node_index(node_ids: tuple[NodeId, ...]) -> dict[NodeId, int]:
    """Cached O(1) mapping from NodeId to first positional index in ContentAST."""
    index: dict[NodeId, int] = {}
    for idx, nid in enumerate(node_ids):
        if nid not in index:
            index[nid] = idx
    return index


@lru_cache(maxsize=256)
def _compute_ast_hash(node_ids: tuple[NodeId, ...]) -> str:
    return content_hash(":".join(node_ids).encode("utf-8"))


class ContentAST(BaseModel, frozen=True):
    """Immutable sequence of content nodes. This is what checks receive."""

    nodes: tuple[Node, ...]

    @property
    def _node_ids(self) -> tuple[NodeId, ...]:
        return tuple(n.id for n in self.nodes)

    @property
    def hash(self) -> str:
        """Deterministic content hash over the ordered sequence of node IDs."""
        return _compute_ast_hash(self._node_ids)

    def __iter__(self) -> Iterator[Node]:  # type: ignore[override]
        return iter(self.nodes)

    def __len__(self) -> int:
        return len(self.nodes)

    def __bool__(self) -> bool:
        return len(self.nodes) > 0

    def __contains__(self, item: object) -> bool:
        if isinstance(item, (TextNode, ImageNode)):
            return item.id in _build_node_index(self._node_ids)
        if isinstance(item, str):
            return NodeId(item) in _build_node_index(self._node_ids)
        return False

    @overload
    def __getitem__(self, idx: int) -> Node: ...

    @overload
    def __getitem__(self, idx: slice) -> ContentAST: ...

    @overload
    def __getitem__(self, idx: NodeId | str) -> Node: ...

    def __getitem__(self, idx: int | slice | NodeId | str) -> Node | ContentAST:
        if isinstance(idx, int):
            return self.nodes[idx]
        if isinstance(idx, slice):
            return ContentAST(nodes=self.nodes[idx])
        pos = _build_node_index(self._node_ids).get(NodeId(idx))
        if pos is None:
            raise KeyError(f"NodeId {idx!r} not found in ContentAST")
        return self.nodes[pos]

    def __add__(self, other: ContentAST) -> ContentAST:
        if not isinstance(other, ContentAST):
            return NotImplemented
        return ContentAST(nodes=self.nodes + other.nodes)

    def index_of(self, node_id: NodeId, default: int = 999_999) -> int:
        """Return the 0-based positional index of `node_id` in O(1) time."""
        return _build_node_index(self._node_ids).get(node_id, default)

    def of_kind(self, kind: NodeKind) -> Iterator[Node]:
        """Yield only nodes matching the given kind."""
        return (n for n in self.nodes if n.kind == kind)

    @classmethod
    def from_texts(cls, texts: list[str]) -> ContentAST:
        """Convenience: build an AST from a list of plain strings."""
        nodes = tuple(TextNode.from_text(t, path=f"p[{i}]") for i, t in enumerate(texts))
        return cls(nodes=nodes)
