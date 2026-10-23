"""Runner: executes checks against a ContentAST and streams Findings.

The runner:
1. Discovers all registered checks
2. For each node x matching check, dispatches work (plus any `run_bundle` checks)
3. Streams findings as they arrive (used for SSE)
4. Caches results by (check_id, check_version, node.id, canon.hash)
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
import time
from collections import OrderedDict
from collections.abc import AsyncIterator

from canongate.domain.ast import ContentAST, Node
from canongate.domain.canon import Canon
from canongate.domain.finding import Finding
from canongate.engine.check import Check

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


# ── True O(1) OrderedDict LRU cache ──────────────────────────────────

_CacheKey = tuple[str, str, str, str]  # (check_id, check_version, node_id, canon_hash)
_cache: OrderedDict[_CacheKey, tuple[Finding, ...]] = OrderedDict()
_CACHE_MAX = 2048


def _cache_key(check: Check, node: Node, canon: Canon) -> _CacheKey:
    return (check.check_id, check.check_version, node.id, canon.hash)


def _cache_get(key: _CacheKey) -> list[Finding] | None:
    entry = _cache.get(key)
    if entry is not None:
        _cache.move_to_end(key)
        return list(entry)
    return None


def _cache_put(key: _CacheKey, findings: list[Finding]) -> None:
    _cache[key] = tuple(findings)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def _stamp_latency(findings: list[Finding], elapsed_ms: float) -> list[Finding]:
    """Populate `trace.latency_ms` on findings that did not set it explicitly."""
    rounded = round(elapsed_ms, 2)
    stamped: list[Finding] = []
    for f in findings:
        if f.trace.latency_ms is None:
            new_trace = f.trace.model_copy(update={"latency_ms": rounded})
            stamped.append(f.model_copy(update={"trace": new_trace}))
        else:
            stamped.append(f)
    return stamped


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
            findings = _stamp_latency(findings, elapsed)
            _cache_put(key, findings)
        return findings

    async def _run_bundle_one(check: Check) -> list[Finding]:
        key: _CacheKey = (check.check_id, check.check_version, f"bundle:{ast.hash}", canon.hash)
        cached = _cache_get(key)
        if cached is not None:
            return cached

        t0 = time.monotonic()
        succeeded = False
        try:
            if type(check).run_bundle_async is not Check.run_bundle_async:
                coro = check.run_bundle_async(ast, canon)
            else:
                coro = asyncio.to_thread(check.run_bundle, ast, canon)
            findings = await asyncio.wait_for(coro, timeout=check.timeout_s)
            succeeded = True
        except Exception:
            logger.exception("Bundle check %s failed on AST %s", check.check_id, ast.hash)
            findings = []
        elapsed = (time.monotonic() - t0) * 1000
        if succeeded:
            findings = _stamp_latency(findings, elapsed)
            _cache_put(key, findings)
        return findings

    # Build task list: each (check, node) pair + cross-node bundle checks when len(ast) > 1
    tasks: list[asyncio.Task[list[Finding]]] = []
    for node in ast:
        for check in checks:
            if check.accepts(node):
                task = asyncio.create_task(_run_one(check, node))
                tasks.append(task)

    if len(ast) > 1:
        for check in checks:
            if (
                type(check).run_bundle is not Check.run_bundle
                or type(check).run_bundle_async is not Check.run_bundle_async
            ):
                tasks.append(asyncio.create_task(_run_bundle_one(check)))

    # Stream results as they complete (deduplicating by finding.id)
    seen_ids: set[str] = set()
    for coro in asyncio.as_completed(tasks):
        findings = await coro
        for f in findings:
            fid = str(f.id)
            if fid not in seen_ids:
                seen_ids.add(fid)
                yield f


async def run_checks_collect(ast: ContentAST, canon: Canon) -> list[Finding]:
    """Run all checks and collect findings into a deterministically sorted list."""
    results: list[Finding] = []
    async for finding in run_checks(ast, canon):
        results.append(finding)
    results.sort(
        key=lambda f: (
            ast.index_of(f.node_id),
            f.locator.sort_key,
            -f.severity,
            f.check_id,
            str(f.id),
        )
    )
    return results
