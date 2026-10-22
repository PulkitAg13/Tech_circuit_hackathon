"""Shared type aliases and small value objects used across the domain."""

from __future__ import annotations

import hashlib
from typing import NewType

NodeId = NewType("NodeId", str)
FindingId = NewType("FindingId", str)
CanonHash = NewType("CanonHash", str)


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
