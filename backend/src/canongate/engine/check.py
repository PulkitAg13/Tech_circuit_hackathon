"""Check: the base class for all governance checks.

Every check:
1. Has a `check_id` (ClassVar) for identity
2. Has a `check_version` (ClassVar) for cache invalidation
3. Declares which NodeKind(s) it processes
4. Implements `run()` — receives one Node + the Canon, yields Findings

Sync checks are dispatched to `asyncio.to_thread` by the runner, so they
never block the event loop. Async checks (ML model inference) override
`run_async()` instead.
"""

from __future__ import annotations

import abc
from typing import ClassVar

from canongate.domain.ast import Node, NodeKind
from canongate.domain.canon import Canon
from canongate.domain.finding import Evidence, Finding, Suggestion
from canongate.domain.types import stable_finding_id
from canongate.engine.registry import _RegistryMixin


class Check(_RegistryMixin, abc.ABC):
    """Abstract base for a governance check.

    Subclass recipe:
        class MyCheck(Check):
            check_id: ClassVar[str] = "my_check"
            check_version: ClassVar[str] = "1.0"
            node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

            def run(self, node: Node, canon: Canon) -> list[Finding]:
                ...
    """

    check_id: ClassVar[str]
    check_version: ClassVar[str]
    node_kinds: ClassVar[frozenset[NodeKind]]

    @abc.abstractmethod
    def run(self, node: Node, canon: Canon) -> list[Finding]:
        """Produce findings for a single node. May be CPU-bound (sync)."""
        ...

    async def run_async(self, node: Node, canon: Canon) -> list[Finding]:
        """Override for I/O-bound or GPU checks. Default delegates to sync."""
        return self.run(node, canon)

    @classmethod
    def accepts(cls, node: Node) -> bool:
        return NodeKind(node.kind) in cls.node_kinds

    # ── Convenience helpers for check authors ────────────────────────

    def finding(
        self,
        *,
        node: Node,
        locator_key: str,
        message: str,
        severity: int,
        evidence: Evidence | None = None,
        suggestion: Suggestion | None = None,
    ) -> Finding:
        """Build a Finding with auto-filled check metadata and stable ID.

        Eliminates boilerplate in `run()`. The `locator_key` should be a
        value unique within this (check, node) pair — e.g. the matched
        span text or rule id — so re-scans produce the same finding ID.
        """
        return Finding(
            id=stable_finding_id(
                self.check_id,
                self.check_version,
                node.id,
                locator_key,
            ),
            check_id=self.check_id,
            check_version=self.check_version,
            node_id=node.id,
            message=message,
            severity=severity,
            evidence=evidence,
            suggestion=suggestion,
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={self.check_id} v={self.check_version}>"
