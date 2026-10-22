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
from canongate.domain.canon import Canon, Rule
from canongate.domain.finding import Evidence, Finding, Locator, Suggestion, Tier, Trace
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
    timeout_s: ClassVar[float] = 10.0

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
        locator: Locator,
        message: str,
        severity: int,
        rule_ref: Rule,
        evidence: Evidence,
        suggestion: Suggestion | None = None,
        trace: Trace | None = None,
        locator_key: str | None = None,
    ) -> Finding:
        """Build a Finding with auto-filled check metadata and stable ID.

        Eliminates boilerplate in `run()`. Defaults `locator_key` to
        `locator.key` (e.g. `s:10-15` or `b:0,0,100,40`) so re-scans
        produce the exact same deterministic FindingId.
        """
        key = locator_key if locator_key is not None else locator.key
        return Finding(
            id=stable_finding_id(
                self.check_id,
                self.check_version,
                node.id,
                key,
            ),
            check_id=self.check_id,
            node_id=node.id,
            locator=locator,
            severity=severity,
            message=message,
            rule_ref=rule_ref,
            evidence=evidence,
            suggestion=suggestion,
            trace=trace if trace is not None else Trace(tier=Tier.DETERMINISTIC),
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={self.check_id} v={self.check_version}>"
