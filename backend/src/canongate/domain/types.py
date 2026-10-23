"""Shared type aliases, Pydantic v1/v2 compatibility helpers, and value objects."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, NewType, TypeVar

from pydantic import BaseModel

NodeId = NewType("NodeId", str)
FindingId = NewType("FindingId", str)
CanonHash = NewType("CanonHash", str)

_F = TypeVar("_F", bound=Callable[..., Any])

try:
    from pydantic import computed_field as _pydantic_computed_field  # type: ignore[attr-defined]

    computed_field = _pydantic_computed_field
except ImportError:

    def computed_field(func: _F) -> _F:  # type: ignore[misc] # noqa: UP047
        """Fallback decorator when running under Pydantic v1."""
        return func


try:
    from pydantic import ConfigDict

    class FrozenModel(BaseModel):
        """Base model supporting frozen=True, model_copy, and model_dump_json
        across Pydantic v1/v2.
        """

        model_config = ConfigDict(frozen=True)

        def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> Any:
            if hasattr(super(), "model_copy"):
                return super().model_copy(update=update, deep=deep)  # type: ignore[misc]
            return self.copy(update=update, deep=deep)

        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            if hasattr(super(), "model_dump"):
                return super().model_dump(**kwargs)  # type: ignore[misc]
            return self.dict(**kwargs)

        def model_dump_json(self, **kwargs: Any) -> str:
            if hasattr(super(), "model_dump_json"):
                return super().model_dump_json(**kwargs)  # type: ignore[misc]
            return self.json(**kwargs)

except ImportError:

    class FrozenModel(BaseModel):  # type: ignore[no-redef]
        """Base model supporting frozen=True, model_copy, and model_dump_json
        across Pydantic v1/v2.
        """

        class Config:
            allow_mutation = False
            frozen = True

        def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> Any:
            return self.copy(update=update, deep=deep)

        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            return self.dict(**kwargs)

        def model_dump_json(self, **kwargs: Any) -> str:
            return self.json(**kwargs)


def content_hash(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes. Used for node IDs and asset hashes."""
    return hashlib.sha256(data).hexdigest()


def text_node_id(text: str) -> NodeId:
    return NodeId(content_hash(text.encode()))


def stable_finding_id(
    check_id: str, check_version: str, node_id: NodeId, locator_key: str
) -> FindingId:
    """Deterministic finding identity: same check + same content + same location = same id."""
    raw = f"{check_id}:{check_version}:{node_id}:{locator_key}"
    return FindingId(content_hash(raw.encode())[:16])
