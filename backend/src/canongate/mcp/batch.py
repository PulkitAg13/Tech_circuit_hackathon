"""Fault-tolerant asynchronous batch governance runner (`canongate.mcp.batch`).

Implements the Round 2 / Round 3 `canongate-mcp` batch execution architecture:
1. **By-Reference Asset Ingestion:** Accepts file paths, directories, globs, or inline
   items without stuffing raw megabytes of documents/banners into LLM tool arguments.
2. **Streaming SHA-256 & Content-Hash Deduplication:** Hashes files in 64 KB chunks
   and memoizes `(canon_hash, alpha, content_hash)` evaluations so repeated assets or
   shared campaign templates across a 100–1,000+ file batch are parsed and scanned once.
3. **Bounded Concurrency & Backpressure:** Uses `asyncio.Semaphore` (`max_concurrency=8`)
   and per-asset timeout guards (`asset_timeout_s=30.0`) so CPU/OCR/Z3 work never
   starves the event loop.
4. **Per-Asset Bulkhead Isolation:** A corrupted PDF/PNG or unreadable path marks only
   that individual asset as `failed` while the remaining batch items complete normally.
5. **Short-Lived Persistence Transactions:** Persists each audited bundle and its
   calibrated findings via `canongate.store.repos` in isolated async sessions after
   CPU/check execution completes, avoiding SQLite lock contention.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import glob
import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from canongate.domain.ast import ContentAST, ImageNode, Node, NodeKind, TextNode
from canongate.domain.canon import Canon
from canongate.domain.finding import Finding
from canongate.domain.types import content_hash
from canongate.engine.conformal import default_calibrator
from canongate.engine.runner import run_checks_collect
from canongate.parsers.bundle import default_bundle_parser
from canongate.parsers.tables import parse_markdown_text
from canongate.parsers.text import parse_text
from canongate.store import init_db, repos
from canongate.store.db import async_session

logger = logging.getLogger(__name__)

SUPPORTED_ASSET_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".json",
        ".yaml",
        ".yml",
        ".html",
        ".htm",
        ".docx",
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }
)

MAX_FILE_BYTES: int = 50 * 1024 * 1024  # 50 MB per asset safety ceiling
MAX_BATCH_ASSETS: int = 2000

JobStatusLiteral = Literal["working", "completed", "failed", "cancelled"]
ItemStatusLiteral = Literal["pending", "running", "completed", "failed", "cancelled"]
GateDecisionLiteral = Literal["allow", "needs_review", "block"]


def parse_raw_bundle_ast(raw: str) -> ContentAST:
    """Parse raw submission text into a `ContentAST`, linearizing Markdown pipe tables."""
    base_ast = parse_text(raw)
    expanded_nodes: list[Node] = []
    for node in base_ast:
        if isinstance(node, TextNode) and node.text.startswith("[HIDDEN_BLOCK] "):
            clean_txt = node.text[len("[HIDDEN_BLOCK] ") :].strip()
            expanded_nodes.append(TextNode.from_text(clean_txt, path=f"{node.path}/hidden[0]"))
            continue
        if isinstance(node, TextNode) and node.text.startswith("[HTML_IMG_MISSING_ALT] "):
            img_src = node.text[len("[HTML_IMG_MISSING_ALT] ") :].strip() or "img"
            expanded_nodes.append(
                ImageNode.from_bytes(
                    img_src.encode("utf-8"),
                    path=img_src,
                    width=100,
                    height=100,
                    alt="",
                )
            )
            continue
        if isinstance(node, TextNode) and "|" in node.text and "\n" in node.text:
            tbl_ast = parse_markdown_text(node.text, source=node.path)
            if any("/table[" in n.path for n in tbl_ast):
                expanded_nodes.extend(tbl_ast.nodes)
                continue
        expanded_nodes.append(node)
    return ContentAST(nodes=tuple(expanded_nodes))


def _load_canon_by_id(canon_id: str) -> Canon:
    from canongate.api.deps import get_canon

    return get_canon(canon_id)


def _stream_file_sha256(path: Path) -> tuple[str, int]:
    """Compute SHA-256 hex digest and byte length of `path` in 64 KB chunks."""
    hasher = hashlib.sha256()
    total = 0
    with path.open("rb") as fh:
        while chunk := fh.read(65536):
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ValueError(
                    f"File {path.name!r} exceeds maximum allowed size ({MAX_FILE_BYTES} bytes)"
                )
            hasher.update(chunk)
    return hasher.hexdigest(), total


@dataclass(frozen=True, slots=True)
class BatchAssetInput:
    """Normalized descriptor for a single asset inside a batch job."""

    title: str
    source_ref: str
    file_path: Path | None = None
    inline_text: str | None = None
    image_paths: tuple[str, ...] = ()

    @property
    def is_file_ref(self) -> bool:
        return self.file_path is not None

    def identity_token(self) -> str:
        """Deterministic token used to compute batch idempotency keys."""
        if self.file_path is not None:
            try:
                st = self.file_path.stat()
                return f"file:{self.file_path.resolve()}:{st.st_size}:{st.st_mtime_ns}"
            except OSError:
                return f"file_missing:{self.source_ref}"
        inline_digest = content_hash((self.inline_text or "").encode("utf-8"))[:16]
        imgs = ",".join(self.image_paths)
        return f"inline:{self.title}:{inline_digest}:{imgs}"


@dataclass(frozen=True, slots=True)
class AssetAuditOutcome:
    """Immutable audit result for a single asset within a `BatchJob`."""

    index: int
    title: str
    source_ref: str
    status: ItemStatusLiteral
    submission_id: int | None = None
    content_hash: str = ""
    node_count: int = 0
    blocker_count: int = 0
    warning_count: int = 0
    findings: tuple[Finding, ...] = ()
    finding_row_ids: tuple[int, ...] = ()
    elapsed_ms: float = 0.0
    cached_hit: bool = False
    error: str | None = None

    @property
    def decision(self) -> GateDecisionLiteral:
        if self.status == "failed" or self.blocker_count > 0:
            return "block"
        if self.warning_count > 0:
            return "needs_review"
        return "allow"

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def studio_url(self) -> str | None:
        if self.submission_id is None:
            return None
        return f"/#/submissions/{self.submission_id}"

    def to_compact_dict(self) -> dict[str, Any]:
        """Compact summary (< 220 bytes) for cursor-paginated rollups."""
        out: dict[str, Any] = {
            "index": self.index,
            "title": self.title[:64],
            "source_ref": Path(self.source_ref).name
            if not self.source_ref.startswith("inline://")
            else self.source_ref,
            "status": self.status,
            "decision": self.decision,
            "blockers": self.blocker_count,
            "warnings": self.warning_count,
            "latency_ms": round(self.elapsed_ms, 2),
        }
        if self.submission_id is not None:
            out["submission_id"] = self.submission_id
            out["studio_url"] = self.studio_url
        if self.cached_hit:
            out["cached"] = True
        if self.error:
            out["error"] = self.error[:120]
        return out


@dataclass(slots=True)
class BatchJob:
    """Stateful batch governance job supporting both MCP Tasks (`tasks/get`) and `job_status`."""

    job_id: str
    idempotency_key: str
    canon_id: str
    canon_version: str
    canon_hash: str
    alpha: float
    conformal_threshold: float
    inputs: tuple[BatchAssetInput, ...]
    status: JobStatusLiteral = "working"
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    completed_at: str | None = None
    elapsed_ms: float = 0.0
    outcomes: list[AssetAuditOutcome] = field(default_factory=list)
    _cancel_requested: bool = False
    _task: asyncio.Task[None] | None = field(default=None, repr=False)
    _done_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def __len__(self) -> int:
        return len(self.inputs)

    def __bool__(self) -> bool:
        return len(self.inputs) > 0

    def __iter__(self) -> Iterator[AssetAuditOutcome]:
        return iter(self.outcomes)

    def __getitem__(self, idx: int) -> AssetAuditOutcome:
        return self.outcomes[idx]

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    @property
    def completed_items(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "completed")

    @property
    def failed_items(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "failed")

    @property
    def processed_items(self) -> int:
        return len(self.outcomes)

    @property
    def progress_ratio(self) -> float:
        total = len(self.inputs)
        if total == 0:
            return 1.0
        return round(len(self.outcomes) / float(total), 4)

    @property
    def blocker_count(self) -> int:
        return sum(o.blocker_count for o in self.outcomes)

    @property
    def warning_count(self) -> int:
        return sum(o.warning_count for o in self.outcomes)

    @property
    def total_findings(self) -> int:
        return sum(o.total_findings for o in self.outcomes)

    @property
    def allow_assets_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "completed" and o.decision == "allow")

    @property
    def needs_review_assets_count(self) -> int:
        return sum(
            1 for o in self.outcomes if o.status == "completed" and o.decision == "needs_review"
        )

    @property
    def blocked_assets_count(self) -> int:
        return sum(1 for o in self.outcomes if o.decision == "block")

    @property
    def overall_decision(self) -> GateDecisionLiteral:
        if self.failed_items > 0 or self.blocker_count > 0:
            return "block"
        if self.warning_count > 0:
            return "needs_review"
        return "allow"

    def request_cancel(self) -> None:
        self._cancel_requested = True
        if not self.is_terminal:
            self.status = "cancelled"
            self.completed_at = dt.datetime.now(dt.UTC).isoformat()
            self._done_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def wait(self, timeout: float | None = None) -> bool:
        """Wait until the batch job reaches a terminal state (or `timeout` expires)."""
        if self.is_terminal:
            return True
        try:
            await asyncio.wait_for(self._done_event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return self.is_terminal

    def summary_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "canon_id": self.canon_id,
            "canon_version": self.canon_version,
            "canon_hash": self.canon_hash[:16],
            "alpha": self.alpha,
            "conformal_threshold": self.conformal_threshold,
            "total_assets": len(self.inputs),
            "processed_assets": self.processed_items,
            "completed_assets": self.completed_items,
            "failed_assets": self.failed_items,
            "progress_ratio": self.progress_ratio,
            "overall_decision": self.overall_decision,
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "total_findings": self.total_findings,
            "asset_verdicts": {
                "allow": self.allow_assets_count,
                "needs_review": self.needs_review_assets_count,
                "block": self.blocked_assets_count,
            },
            "elapsed_ms": round(self.elapsed_ms, 2),
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "human_signoff_note": (
                "Sign-off stays in the Review Studio; MCP is strictly read/diagnostic."
            ),
        }


def resolve_reference_inputs(
    paths: Sequence[str | Path] = (),
    inline_items: Sequence[dict[str, Any]] = (),
) -> list[BatchAssetInput]:
    """Expand file paths, directories, and globs by reference into `BatchAssetInput` items."""
    resolved: list[BatchAssetInput] = []
    seen_files: set[Path] = set()

    for raw_p in paths:
        p_str = str(raw_p).strip()
        if not p_str:
            continue

        if any(ch in p_str for ch in ("*", "?", "[")):
            matches = sorted(Path(m) for m in glob.glob(p_str, recursive=True))
            for m_path in matches:
                if (
                    m_path.is_file()
                    and m_path.suffix.lower() in SUPPORTED_ASSET_EXTENSIONS
                    and m_path.resolve() not in seen_files
                ):
                    seen_files.add(m_path.resolve())
                    resolved.append(
                        BatchAssetInput(
                            title=m_path.name,
                            source_ref=str(m_path),
                            file_path=m_path,
                        )
                    )
            continue

        candidate = Path(p_str)
        if candidate.is_dir():
            for child in sorted(candidate.rglob("*")):
                if (
                    child.is_file()
                    and child.suffix.lower() in SUPPORTED_ASSET_EXTENSIONS
                    and child.resolve() not in seen_files
                ):
                    seen_files.add(child.resolve())
                    resolved.append(
                        BatchAssetInput(
                            title=child.name,
                            source_ref=str(child),
                            file_path=child,
                        )
                    )
            continue

        if candidate.exists() and candidate.is_file():
            seen_files.add(candidate.resolve())
        resolved.append(
            BatchAssetInput(
                title=candidate.name or p_str,
                source_ref=p_str,
                file_path=candidate,
            )
        )

    for idx, item in enumerate(inline_items):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or f"Inline Bundle #{idx + 1}").strip()
        path_val = str(item.get("path") or "").strip()
        text_val = str(item.get("text") or item.get("raw_content") or "").strip()
        img_paths = tuple(str(x).strip() for x in (item.get("image_paths") or ()) if str(x).strip())

        if path_val and not text_val:
            f_path = Path(path_val)
            resolved.append(
                BatchAssetInput(
                    title=title or f_path.name,
                    source_ref=path_val,
                    file_path=f_path,
                    image_paths=img_paths,
                )
            )
        else:
            resolved.append(
                BatchAssetInput(
                    title=title,
                    source_ref=f"inline://{idx + 1}/{title.replace(' ', '_')[:32]}",
                    file_path=None,
                    inline_text=text_val,
                    image_paths=img_paths,
                )
            )

    if len(resolved) > MAX_BATCH_ASSETS:
        raise ValueError(
            f"Batch size {len(resolved)} exceeds maximum allowed ({MAX_BATCH_ASSETS} assets)."
        )
    return resolved


class BatchJobManager:
    """High-performance, fault-tolerant async batch manager for `canongate-mcp`."""

    __slots__ = (
        "_asset_memo",
        "_asset_timeout_s",
        "_db_initialized",
        "_idempotency_index",
        "_jobs",
        "_max_concurrency",
        "_max_jobs",
        "_semaphore",
    )

    def __init__(
        self,
        *,
        max_concurrency: int = 8,
        asset_timeout_s: float = 30.0,
        max_jobs: int = 256,
    ) -> None:
        self._max_concurrency = max(1, max_concurrency)
        self._asset_timeout_s = max(1.0, asset_timeout_s)
        self._max_jobs = max(16, max_jobs)
        self._semaphore: asyncio.Semaphore | None = None
        self._jobs: OrderedDict[str, BatchJob] = OrderedDict()
        self._idempotency_index: dict[str, str] = {}
        self._asset_memo: OrderedDict[
            tuple[str, float, str], tuple[str, tuple[Finding, ...], int]
        ] = OrderedDict()
        self._db_initialized: bool = False

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrency)
        return self._semaphore

    async def _ensure_db(self) -> None:
        if not self._db_initialized:
            await init_db()
            self._db_initialized = True

    def __len__(self) -> int:
        return len(self._jobs)

    def __contains__(self, job_id: object) -> bool:
        return isinstance(job_id, str) and job_id in self._jobs

    def get_job(self, job_id: str) -> BatchJob | None:
        job = self._jobs.get(job_id)
        if job is not None:
            self._jobs.move_to_end(job_id)
        return job

    def list_jobs(self) -> list[BatchJob]:
        return list(reversed(self._jobs.values()))

    @staticmethod
    def _compute_idempotency_key(
        canon_hash: str,
        alpha: float,
        inputs: Sequence[BatchAssetInput],
        persist: bool,
    ) -> str:
        raw = json.dumps(
            {
                "canon_hash": canon_hash,
                "alpha": round(alpha, 4),
                "persist": persist,
                "assets": [inp.identity_token() for inp in inputs],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def submit_batch(
        self,
        *,
        canon_id: str,
        paths: Sequence[str | Path] = (),
        inline_items: Sequence[dict[str, Any]] = (),
        alpha: float = 0.10,
        persist: bool = True,
        wait_for_completion: bool = False,
        wait_timeout_s: float = 5.0,
        force_new: bool = False,
    ) -> BatchJob:
        """Create or reuse an idempotent `BatchJob` and schedule concurrent background scanning."""
        canon = _load_canon_by_id(canon_id)
        clamped_alpha = max(0.01, min(0.25, round(float(alpha), 4)))
        inputs = tuple(resolve_reference_inputs(paths=paths, inline_items=inline_items))
        if not inputs:
            raise ValueError(
                "Batch submission requires at least one file path, directory, or item."
            )

        idem_key = self._compute_idempotency_key(canon.hash, clamped_alpha, inputs, persist)
        if not force_new and idem_key in self._idempotency_index:
            existing_id = self._idempotency_index[idem_key]
            existing_job = self._jobs.get(existing_id)
            if existing_job is not None and existing_job.status in ("working", "completed"):
                if wait_for_completion:
                    await existing_job.wait(timeout=wait_timeout_s)
                return existing_job

        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = BatchJob(
            job_id=job_id,
            idempotency_key=idem_key,
            canon_id=canon.id,
            canon_version=canon.version,
            canon_hash=canon.hash,
            alpha=clamped_alpha,
            conformal_threshold=default_calibrator.threshold(clamped_alpha),
            inputs=inputs,
            status="working",
        )
        self._jobs[job_id] = job
        self._idempotency_index[idem_key] = job_id
        while len(self._jobs) > self._max_jobs:
            _, old_job = self._jobs.popitem(last=False)
            self._idempotency_index.pop(old_job.idempotency_key, None)

        task = asyncio.create_task(self._execute_job(job, canon, persist=persist))
        job._task = task

        if wait_for_completion:
            await job.wait(timeout=wait_timeout_s)
        return job

    async def _execute_job(self, job: BatchJob, canon: Canon, *, persist: bool) -> None:
        t0 = time.perf_counter()
        try:
            if persist:
                await self._ensure_db()

            sem = self._get_semaphore()
            ordered_outcomes: list[AssetAuditOutcome | None] = [None] * len(job.inputs)

            async def _worker(idx: int, asset: BatchAssetInput) -> None:
                if job._cancel_requested:
                    outcome = AssetAuditOutcome(
                        index=idx,
                        title=asset.title,
                        source_ref=asset.source_ref,
                        status="cancelled",
                    )
                    ordered_outcomes[idx] = outcome
                    job.outcomes.append(outcome)
                    return

                async with sem:
                    if job._cancel_requested:
                        return
                    outcome = await self._audit_single_asset(
                        idx=idx,
                        asset=asset,
                        canon=canon,
                        alpha=job.alpha,
                        persist=persist,
                    )
                    ordered_outcomes[idx] = outcome
                    job.outcomes.append(outcome)
                    job.elapsed_ms = (time.perf_counter() - t0) * 1000.0

            await asyncio.gather(*(_worker(i, inp) for i, inp in enumerate(job.inputs)))
            job.outcomes = [o for o in ordered_outcomes if o is not None]
            job.elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if not job._cancel_requested:
                job.status = "completed"
                job.completed_at = dt.datetime.now(dt.UTC).isoformat()
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.completed_at = dt.datetime.now(dt.UTC).isoformat()
            job.elapsed_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as exc:
            logger.exception("BatchJob %s encountered top-level failure", job.job_id)
            job.status = "failed"
            job.completed_at = dt.datetime.now(dt.UTC).isoformat()
            job.elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if not job.outcomes:
                job.outcomes.append(
                    AssetAuditOutcome(
                        index=0,
                        title="batch_error",
                        source_ref="batch",
                        status="failed",
                        error=str(exc),
                    )
                )
        finally:
            job._done_event.set()

    async def _audit_single_asset(
        self,
        *,
        idx: int,
        asset: BatchAssetInput,
        canon: Canon,
        alpha: float,
        persist: bool,
    ) -> AssetAuditOutcome:
        """Fault-isolated per-asset audit bulkhead with content-hash memoization."""
        t0 = time.perf_counter()
        try:
            return await asyncio.wait_for(
                self._audit_single_asset_inner(
                    idx=idx,
                    asset=asset,
                    canon=canon,
                    alpha=alpha,
                    persist=persist,
                    t0=t0,
                ),
                timeout=self._asset_timeout_s,
            )
        except TimeoutError:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return AssetAuditOutcome(
                index=idx,
                title=asset.title,
                source_ref=asset.source_ref,
                status="failed",
                elapsed_ms=elapsed,
                error=f"Asset audit timed out after {self._asset_timeout_s:.1f}s",
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return AssetAuditOutcome(
                index=idx,
                title=asset.title,
                source_ref=asset.source_ref,
                status="failed",
                elapsed_ms=elapsed,
                error=str(exc),
            )

    async def _audit_single_asset_inner(
        self,
        *,
        idx: int,
        asset: BatchAssetInput,
        canon: Canon,
        alpha: float,
        persist: bool,
        t0: float,
    ) -> AssetAuditOutcome:
        if asset.file_path is not None:
            fpath = asset.file_path
            if not fpath.exists() or not fpath.is_file():
                raise FileNotFoundError(f"Asset file not found: {fpath}")
            ext = fpath.suffix.lower()
            if ext not in SUPPORTED_ASSET_EXTENSIONS:
                raise ValueError(f"Unsupported file extension {ext!r} for {fpath.name}")
            file_sha, file_size = await asyncio.to_thread(_stream_file_sha256, fpath)
            if file_size == 0:
                raise ValueError(f"Asset file is empty (0 bytes): {fpath.name}")
            c_hash = file_sha
        else:
            raw_inline = (asset.inline_text or "").strip()
            if asset.image_paths:
                extra_md = "\n\n".join(
                    f"![Banner]({p})" for p in asset.image_paths if p not in raw_inline
                )
                if extra_md:
                    raw_inline = f"{raw_inline}\n\n{extra_md}".strip()
            if not raw_inline:
                raise ValueError(f"Inline asset {asset.title!r} has empty content")
            c_hash = content_hash(raw_inline.encode("utf-8"))

        memo_key = (canon.hash, round(alpha, 4), c_hash)
        cached_entry = self._asset_memo.get(memo_key)
        cached_hit = False

        if cached_entry is not None:
            self._asset_memo.move_to_end(memo_key)
            raw_content, calibrated_tuple, node_count = cached_entry
            calibrated = list(calibrated_tuple)
            cached_hit = True
        else:
            if asset.file_path is not None:
                fpath = asset.file_path
                ext = fpath.suffix.lower()
                if ext in {".png", ".jpg", ".jpeg", ".webp"}:
                    ast: ContentAST = await asyncio.to_thread(
                        default_bundle_parser.parse_one, fpath
                    )
                    if len(ast) == 0:
                        raise ValueError(f"Corrupted or unreadable image file: {fpath.name}")
                    ocr_lines = [
                        n.text.strip()
                        for n in ast.of_kind(NodeKind.TEXT)
                        if isinstance(n, TextNode) and n.text.strip()
                    ]
                    raw_parts = [*ocr_lines, f"![Banner]({fpath.resolve()})"]
                    raw_content = "\n\n".join(raw_parts)
                else:
                    ast = await asyncio.to_thread(default_bundle_parser.parse_one, fpath)
                    if len(ast) == 0:
                        raise ValueError(f"Corrupted, empty, or unparseable document: {fpath.name}")
                    text_blocks: list[str] = []
                    for node in ast:
                        if isinstance(node, TextNode) and node.text.strip():
                            if "/hidden[" in node.path:
                                text_blocks.append(f"[HIDDEN_BLOCK] {node.text.strip()}")
                            else:
                                text_blocks.append(node.text.strip())
                        elif isinstance(node, ImageNode):
                            if node.alt == "" and not Path(node.asset_path).is_file():
                                text_blocks.append(f"[HTML_IMG_MISSING_ALT] {node.asset_path}")
                            elif node.asset_path:
                                text_blocks.append(f"![Banner]({node.asset_path})")
                    raw_content = "\n\n".join(text_blocks)
            else:
                raw_content = (asset.inline_text or "").strip()
                if asset.image_paths:
                    extra_md = "\n\n".join(
                        f"![Banner]({p})" for p in asset.image_paths if p not in raw_content
                    )
                    if extra_md:
                        raw_content = f"{raw_content}\n\n{extra_md}".strip()
                ast = await asyncio.to_thread(parse_raw_bundle_ast, raw_content)
                if len(ast) == 0:
                    raise ValueError(f"Asset {asset.title!r} produced an empty AST")

            node_count = len(ast)
            raw_findings = await run_checks_collect(ast, canon)
            calibrated = default_calibrator.filter_and_calibrate_findings(raw_findings, alpha=alpha)
            self._asset_memo[memo_key] = (raw_content, tuple(calibrated), node_count)
            while len(self._asset_memo) > 512:
                self._asset_memo.popitem(last=False)

        sub_id: int | None = None
        row_ids: tuple[int, ...] = ()
        if persist:
            async with async_session() as session, session.begin():
                sub = await repos.create_submission(
                    session,
                    title=asset.title,
                    raw_content=raw_content,
                    content_hash=c_hash,
                    canon_id=canon.id,
                    canon_hash=canon.hash,
                    creator_id=1,
                )
                sub_id = sub.id
                await repos.save_findings(session, sub.id, calibrated)
                saved_rows = await repos.get_findings_for_submission(session, sub.id)
                row_ids = tuple(r.id for r in saved_rows)

        blockers = sum(1 for f in calibrated if f.is_blocker)
        warnings = sum(1 for f in calibrated if f.is_warning)
        elapsed = (time.perf_counter() - t0) * 1000.0

        return AssetAuditOutcome(
            index=idx,
            title=asset.title,
            source_ref=asset.source_ref,
            status="completed",
            submission_id=sub_id,
            content_hash=c_hash,
            node_count=node_count,
            blocker_count=blockers,
            warning_count=warnings,
            findings=tuple(calibrated),
            finding_row_ids=row_ids,
            elapsed_ms=elapsed,
            cached_hit=cached_hit,
        )


default_batch_manager = BatchJobManager()
