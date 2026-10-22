"""Runner: executes checks against a ContentAST and streams Findings.

The runner:
1. Discovers all registered checks
2. For each node x matching check, dispatches work
3. Streams findings as they arrive (used for SSE)
4. Caches results by (check_id, check_version, node.id, canon.hash)
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from canongate.domain.ast import ContentAST, Node
from canongate.domain.canon import Canon
from canongate.domain.finding import Finding
from canongate.engine.check import Check

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _discover_checks(package_name: str = "canongate.checks") -> None:
    """Import all modules under the checks package so __init_subclass__ fires."""
    try:
        pkg = importlib.import_module(package_name)
    except ModuleNotFoundError:
        logger.warning("Checks package %r not found, no checks will run.", package_name)
        return

    if pkg.__path__ is None:
        return

    for _finder, name, _ispkg in pkgutil.walk_packages(pkg.__path__, prefix=f"{package_name}."):
        try:
            importlib.import_module(name)
        except Exception:
            logger.exception("Failed to import check module %s", name)


# Ensure checks are discovered on first import of the runner
_discover_checks()


def _instantiate_checks() -> list[Check]:
    """Instantiate all registered checks. Called once per run."""
    return [cls() for cls in Check.get_all().values()]


# ── Simple in-memory LRU cache ───────────────────────────────────────

_CacheKey = tuple[str, str, str, str]  # (check_id, check_version, node_id, canon_hash)
_cache: dict[_CacheKey, tuple[Finding, ...]] = {}
_CACHE_MAX = 2048


def _cache_key(check: Check, node: Node, canon: Canon) -> _CacheKey:
    return (check.check_id, check.check_version, node.id, canon.hash)


def _cache_get(key: _CacheKey) -> list[Finding] | None:
    entry = _cache.get(key)
    return list(entry) if entry is not None else None


def _cache_put(key: _CacheKey, findings: list[Finding]) -> None:
    if len(_cache) >= _CACHE_MAX:
        # Evict oldest 25%
        keys_to_drop = list(_cache.keys())[: _CACHE_MAX // 4]
        for k in keys_to_drop:
            del _cache[k]
    _cache[key] = tuple(findings)


# ── Runner ───────────────────────────────────────────────────────────


async def run_checks(ast: ContentAST, canon: Canon) -> AsyncIterator[Finding]:
    """Run all registered checks on the AST and yield findings as they arrive."""
    checks = _instantiate_checks()

    async def _run_one(check: Check, node: Node) -> list[Finding]:
        key = _cache_key(check, node, canon)
        cached = _cache_get(key)
        if cached is not None:
            logger.debug("Cache hit: %s on %s", check.check_id, node.id)
            return cached

        t0 = time.monotonic()
        succeeded = False
        try:
            if type(check).run_async is not Check.run_async:
                coro = check.run_async(node, canon)
            else:
                # Sync checks go to a thread to avoid blocking the event loop
                coro = asyncio.to_thread(check.run, node, canon)
            findings = await asyncio.wait_for(coro, timeout=check.timeout_s)
            succeeded = True
        except Exception:
            logger.exception("Check %s failed on node %s", check.check_id, node.id)
            findings = []
        elapsed = (time.monotonic() - t0) * 1000
        logger.debug(
            "Check %s on %s: %d findings in %.1fms",
            check.check_id,
            node.id,
            len(findings),
            elapsed,
        )

        # Never cache failed or timed-out runs — caching `[]` on error poisons
        # subsequent scans into silently reporting 0 findings (PASS).
        if succeeded:
            _cache_put(key, findings)
        return findings

    # Build task list: each (check, node) pair
    tasks: list[asyncio.Task[list[Finding]]] = []
    for node in ast:
        for check in checks:
            if check.accepts(node):
                task = asyncio.create_task(_run_one(check, node))
                tasks.append(task)

    # Stream results as they complete
    for coro in asyncio.as_completed(tasks):
        findings = await coro
        for f in findings:
            yield f


async def run_checks_collect(ast: ContentAST, canon: Canon) -> list[Finding]:
    """Run all checks and collect findings into a deterministically sorted list."""
    node_order = {node.id: idx for idx, node in enumerate(ast.nodes)}
    results: list[Finding] = []
    async for finding in run_checks(ast, canon):
        results.append(finding)
    results.sort(
        key=lambda f: (
            node_order.get(f.node_id, 999999),
            f.locator.key,
            f.check_id,
            str(f.id),
        )
    )
    return results
