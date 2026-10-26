"""CanonGate MCP (`canongate-mcp`) JSON-RPC 2.0 Server (`stdio` + Streamable HTTP).

Implements the official Model Context Protocol (`2026-07-28` specification with
backward compatibility for `2025-03-26` clients) over two transports:
  1. `stdio`: newline-delimited JSON-RPC 2.0 over `stdin`/`stdout` (zero `stdout`
     logging pollution; all diagnostics strictly routed to `stderr`).
  2. Streamable HTTP (`POST /api/mcp`): single endpoint accepting JSON-RPC 2.0
     with `MCP-Protocol-Version: 2026-07-28`, `Origin` DNS-rebinding defense,
     and HTTP security routing headers (`Mcp-Method`, `Mcp-Name`, `Mcp-Param-*`)
     raising `-32020 HeaderMismatch` on spoofing.

Architectural invariants enforced:
  - Exposes ONLY 6 read-only/diagnostic governance tools:
      1. `list_canons`
      2. `submit_batch`
      3. `job_status`
      4. `get_findings`
      5. `explain_finding`
      6. `propose_fix`
  - Explicitly omits and blocks `approve`, `publish`, and `override` tools so human
    sign-off remains exclusively in the Review Studio (OWASP LLM06 defense).
  - Enforces a strict `< 4,096` byte (`< 4 KB`) serialized JSON-RPC wire ceiling on
    every response via by-reference file ingestion and opaque cursor pagination.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from typing import Any, TextIO

from canongate.domain.ast import NodeKind, TextNode
from canongate.domain.canon import Canon
from canongate.domain.finding import Finding
from canongate.engine.rewriter import default_constrained_rewriter
from canongate.engine.runner import run_checks_collect
from canongate.mcp.batch import (
    BatchJob,
    BatchJobManager,
    default_batch_manager,
    parse_raw_bundle_ast,
)
from canongate.store import repos
from canongate.store.db import async_session, init_db

logger = logging.getLogger(__name__)


def _list_canon_ids_lazy() -> list[str]:
    from canongate.api.deps import list_canon_ids

    return list_canon_ids()


def _get_canon_lazy(canon_id: str) -> Canon:
    from canongate.api.deps import get_canon

    return get_canon(canon_id)


MAX_MCP_WIRE_BYTES = 4096
_MAX_STRUCTURED_PAYLOAD_BYTES = 1550

SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2026-07-28",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)

SERVER_INFO: dict[str, str] = {
    "name": "canongate-mcp",
    "title": "CanonGate Brand & Regulatory Governance MCP Server",
    "version": "0.2.0",
}

FORBIDDEN_MUTATION_TOOLS: frozenset[str] = frozenset(
    {
        "approve",
        "approve_submission",
        "publish",
        "publish_submission",
        "override",
        "override_finding",
        "dismiss",
        "dismiss_finding",
        "sign_off",
    }
)


class McpToolError(Exception):
    """Domain-level tool execution error surfaced with `isError: True` per MCP spec."""

    def __init__(self, message: str, *, code: str = "tool_execution_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class McpProtocolError(Exception):
    """JSON-RPC 2.0 protocol error (`-32700`, `-32600`, `-32601`, `-32602`, `-32020`, `-32022`)."""

    def __init__(
        self,
        code: int,
        message: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass(frozen=True, slots=True)
class PageCursor:
    """Opaque URL-safe Base64 pagination token bound to a deterministic query scope."""

    offset: int
    scope: str = ""

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError("Cursor offset cannot be negative")

    def encode(self) -> str:
        payload = json.dumps(
            {"o": self.offset, "s": self.scope},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @classmethod
    def decode(cls, token: str | None, *, expected_scope: str = "") -> PageCursor:
        if not token:
            return cls(offset=0, scope=expected_scope)
        try:
            padded = token + "=" * (-len(token) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("ascii"))
            obj = json.loads(raw.decode("utf-8"))
            if not isinstance(obj, dict) or "o" not in obj:
                raise ValueError("Malformed cursor payload")
            offset = int(obj["o"])
            scope = str(obj.get("s", ""))
            if offset < 0:
                raise ValueError("Cursor offset < 0")
            if expected_scope and scope and scope != expected_scope:
                raise ValueError("Cursor scope mismatch for query parameters")
            return cls(offset=offset, scope=expected_scope or scope)
        except Exception as exc:
            raise McpToolError(
                f"Invalid pagination cursor {token!r}: {exc}. Restart pagination without cursor.",
                code="invalid_cursor",
            ) from exc


def _compact_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _pack_paginated_items(
    items: list[dict[str, Any]],
    *,
    offset: int,
    scope: str,
    max_items_cap: int = 8,
    max_bytes: int = _MAX_STRUCTURED_PAYLOAD_BYTES,
    envelope_builder: Any,
) -> tuple[list[dict[str, Any]], str | None]:
    """Pack a slice of `items[offset:]` so the serialized envelope stays strictly `<= max_bytes`."""
    total = len(items)
    if offset >= total:
        return [], None

    chosen: list[dict[str, Any]] = []
    upper = min(total, offset + max(1, max_items_cap))
    for idx in range(offset, upper):
        candidate_slice = [*chosen, items[idx]]
        next_idx = idx + 1
        tentative_cursor = (
            PageCursor(offset=next_idx, scope=scope).encode() if next_idx < total else None
        )
        envelope = envelope_builder(candidate_slice, tentative_cursor)
        if _byte_len(_compact_json(envelope)) > max_bytes and chosen:
            break
        chosen.append(items[idx])

    next_offset = offset + len(chosen)
    next_cursor = (
        PageCursor(offset=next_offset, scope=scope).encode() if next_offset < total else None
    )
    return chosen, next_cursor


TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "list_canons",
        "title": "List Signed Brand & Regulatory Canons",
        "description": (
            "List active signed Canon rulebooks (terminology, palette, facts, trigger obligations, "
            "logos, voice profile) with rule counts and cryptographic SHA-256 hashes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cursor": {
                    "type": "string",
                    "description": "Opaque pagination cursor from a previous `list_canons` call.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 10,
                    "description": "Maximum canons per page.",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {
            "title": "List Canons",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "submit_batch",
        "title": "Submit By-Reference Multimodal Asset Batch for Audit",
        "description": (
            "Submit 1 to 500 campaign assets by file path, directory, or glob pattern "
            "(.docx, .pdf, .pptx, .html, .md, .csv, .png, .jpg, .webp) or inline bundles "
            "against a signed Canon. Runs async checks and returns a `job_id`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "canon_id": {
                    "type": "string",
                    "description": (
                        "Signed Canon ID (e.g. 'indian-digital-lending', 'indian-d2c-nutra')."
                    ),
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "File paths, directory paths, or glob patterns passed by reference."
                    ),
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "path": {"type": "string"},
                            "text": {"type": "string"},
                            "image_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                    "description": "Optional inline or structured asset descriptors.",
                },
                "alpha": {
                    "type": "number",
                    "minimum": 0.01,
                    "maximum": 0.25,
                    "default": 0.10,
                    "description": (
                        "Split-conformal false-positive miscoverage bound alpha in [0.01, 0.25]."
                    ),
                },
                "wait_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10000,
                    "default": 1500,
                    "description": (
                        "Milliseconds to wait for fast batch completion before returning."
                    ),
                },
            },
            "required": ["canon_id"],
            "additionalProperties": False,
        },
        "execution": {"taskSupport": "optional"},
        "annotations": {
            "title": "Submit Batch Audit",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "job_status",
        "title": "Poll Batch Audit Job Progress & Asset Rollups",
        "description": (
            "Inspect progress, overall gate decision ('allow' | 'needs_review' | 'block'), "
            "blocker/warning totals, and cursor-paginated per-asset outcomes for a `job_id`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Batch job identifier returned by `submit_batch`.",
                },
                "cursor": {
                    "type": "string",
                    "description": "Opaque cursor for paginating per-asset outcomes.",
                },
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Batch Job Status",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "get_findings",
        "title": "List Paginated Findings for a Batch Job or Submission",
        "description": (
            "Retrieve cursor-paginated BLOCKER and WARNING findings (<4KB per page) for a "
            "`job_id` or `submission_id`, with optional filtering by `verdict` or `check_id`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Batch job ID from `submit_batch`.",
                },
                "submission_id": {
                    "type": "integer",
                    "description": "Specific submission ID in the Review Studio.",
                },
                "verdict": {
                    "type": "string",
                    "enum": ["all", "blocker", "warning"],
                    "default": "all",
                    "description": "Filter by two-tier severity verdict.",
                },
                "check_id": {
                    "type": "string",
                    "description": (
                        "Optional filter by check ID (e.g. 'claim.slot_nli', 'palette.delta_e')."
                    ),
                },
                "cursor": {
                    "type": "string",
                    "description": "Opaque cursor from a prior `get_findings` response.",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Get Paginated Findings",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "explain_finding",
        "title": "Inspect Full Typed Evidence & Rule Provenance for a Finding",
        "description": (
            "Return the complete typed evidence (SlotDiff, TriggerObligationEvidence, "
            "DeltaEEvidence, ContrastEvidence, etc.), rule provenance, AST locator, and "
            "execution trace for a specific finding (`row_id` or `finding_id`)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "row_id": {
                    "type": "integer",
                    "description": "Database row ID of the finding (returned in `get_findings`).",
                },
                "finding_id": {
                    "type": "string",
                    "description": "UUID of the finding (`Finding.id`).",
                },
                "submission_id": {
                    "type": "integer",
                    "description": "Optional submission ID containing the finding.",
                },
                "job_id": {
                    "type": "string",
                    "description": "Optional batch job ID containing the finding.",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Explain Finding Evidence",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "propose_fix",
        "title": "Generate Non-Mutating Surgical Fix Preview",
        "description": (
            "Run CanonGate's Tier 3 Constrained Surgical Rewriter (with PII masking, "
            "Levenshtein edit-distance <= 0.35 guard, and Tier 1/2 re-verification) or "
            "visual palette/contrast repair to preview a compliant fix WITHOUT mutating "
            "or approving the submission."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "row_id": {
                    "type": "integer",
                    "description": "Database row ID of the finding.",
                },
                "finding_id": {
                    "type": "string",
                    "description": "UUID of the finding (`Finding.id`).",
                },
                "submission_id": {
                    "type": "integer",
                    "description": "Optional submission ID containing the finding.",
                },
                "job_id": {
                    "type": "string",
                    "description": "Optional batch job ID containing the finding.",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Propose Surgical Fix Preview",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
)

TOOL_MAP: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOL_DEFINITIONS}


class CanonGateMcpServer:
    """Stateless JSON-RPC 2.0 dispatcher for `canongate-mcp` (`stdio` and Streamable HTTP)."""

    __slots__ = ("_batch_manager", "_db_ready")

    def __init__(self, batch_manager: BatchJobManager | None = None) -> None:
        self._batch_manager = batch_manager or default_batch_manager
        self._db_ready = False

    async def _ensure_db(self) -> None:
        if not self._db_ready:
            await init_db()
            self._db_ready = True

    async def handle_jsonrpc(
        self, message: dict[str, Any] | list[Any]
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Process a decoded JSON-RPC 2.0 request, notification, or batch."""
        if isinstance(message, list):
            if not message:
                return self._error_frame(None, -32600, "Invalid Request: empty batch")
            responses: list[dict[str, Any]] = []
            for item in message:
                if isinstance(item, dict):
                    res = await self._handle_single_frame(item)
                    if res is not None:
                        responses.append(res)
                else:
                    responses.append(
                        self._error_frame(None, -32600, "Invalid Request item in batch")
                    )
            return responses if responses else None

        if not isinstance(message, dict):
            return self._error_frame(None, -32600, "Invalid Request: expected JSON object")
        return await self._handle_single_frame(message)

    async def _handle_single_frame(self, message: dict[str, Any]) -> dict[str, Any] | None:
        jsonrpc_ver = message.get("jsonrpc")
        has_id = "id" in message
        req_id = message.get("id")
        method = message.get("method")

        if jsonrpc_ver != "2.0" or not isinstance(method, str) or not method:
            return self._error_frame(
                req_id if has_id else None,
                -32600,
                "Invalid Request: requires jsonrpc='2.0' and non-empty method string",
            )

        if not has_id:
            if method == "notifications/cancelled":
                params = message.get("params") or {}
                task_id = params.get("taskId") or params.get("job_id")
                if isinstance(task_id, str):
                    job = self._batch_manager.get_job(task_id)
                    if job is not None:
                        job.request_cancel()
            return None

        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return self._error_frame(req_id, -32602, "Invalid params: expected JSON object")

        meta = params.get("_meta")
        if isinstance(meta, dict):
            req_ver = meta.get("io.modelcontextprotocol/protocolVersion")
            if isinstance(req_ver, str) and req_ver not in SUPPORTED_PROTOCOL_VERSIONS:
                return self._error_frame(
                    req_id,
                    -32022,
                    f"Unsupported protocol version: {req_ver}",
                    data={"supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS)},
                )

        try:
            if method == "server/discover":
                result = self._handle_discover()
            elif method == "initialize":
                result = self._handle_initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = self._handle_tools_list(params)
            elif method == "tools/call":
                result = await self._handle_tools_call(params)
            elif method == "tasks/get":
                result = await self._handle_tasks_get(params)
            elif method == "tasks/cancel":
                result = self._handle_tasks_cancel(params)
            elif method == "resources/list":
                result = self._handle_resources_list(params)
            elif method == "resources/read":
                result = await self._handle_resources_read(params)
            elif method == "prompts/list":
                result = {"resultType": "complete", "prompts": []}
            else:
                return self._error_frame(req_id, -32601, f"Method not found: {method}")
        except McpProtocolError as p_err:
            return self._error_frame(req_id, p_err.code, p_err.message, data=p_err.data)
        except Exception as exc:
            logger.exception("Unhandled error in MCP method %s", method)
            return self._error_frame(req_id, -32603, f"Internal error: {exc}")

        response = {"jsonrpc": "2.0", "id": req_id, "result": result}
        return self._enforce_wire_budget(response)

    @staticmethod
    def _handle_discover() -> dict[str, Any]:
        return {
            "resultType": "complete",
            "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {},
                "extensions": {
                    "io.modelcontextprotocol/tasks": {},
                },
            },
            "_meta": {
                "io.modelcontextprotocol/serverInfo": dict(SERVER_INFO),
            },
            "ttlMs": 3600000,
            "cacheScope": "public",
        }

    @staticmethod
    def _handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
        requested = str(params.get("protocolVersion") or "2025-03-26")
        negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else "2025-03-26"
        return {
            "protocolVersion": negotiated,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {},
            },
            "serverInfo": dict(SERVER_INFO),
            "instructions": (
                "CanonGate MCP exposes 6 read-only governance tools (list_canons, submit_batch, "
                "job_status, get_findings, explain_finding, propose_fix). Pass files by reference. "
                "Human approval and publishing remain strictly in the Review Studio."
            ),
        }

    @staticmethod
    def _handle_tools_list(params: dict[str, Any]) -> dict[str, Any]:
        cursor_tok = params.get("cursor")
        try:
            cur = PageCursor.decode(cursor_tok, expected_scope="tools_list")
        except McpToolError as exc:
            raise McpProtocolError(-32602, exc.message) from exc

        page, next_cursor = _pack_paginated_items(
            list(TOOL_DEFINITIONS),
            offset=cur.offset,
            scope="tools_list",
            max_items_cap=2,
            max_bytes=2800,
            envelope_builder=lambda items, nxt: {
                "resultType": "complete",
                "tools": items,
                **({"nextCursor": nxt} if nxt else {}),
                "ttlMs": 300000,
                "cacheScope": "public",
            },
        )
        res: dict[str, Any] = {
            "resultType": "complete",
            "tools": page,
            "ttlMs": 300000,
            "cacheScope": "public",
        }
        if next_cursor:
            res["nextCursor"] = next_cursor
        return res

    async def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        tool_name = str(params.get("name") or "").strip()
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise McpProtocolError(-32602, "Tool arguments must be a JSON object")

        if tool_name in FORBIDDEN_MUTATION_TOOLS or any(
            tool_name.startswith(f"{verb}_") for verb in FORBIDDEN_MUTATION_TOOLS
        ):
            return self._tool_error_result(
                f"Tool {tool_name!r} is intentionally unavailable in canongate-mcp. "
                "Per CanonGate responsible design (OWASP LLM06), AI agents cannot approve, "
                "override, or publish campaigns; sign-off stays exclusively in the Review Studio."
            )

        if tool_name not in TOOL_MAP:
            raise McpProtocolError(-32602, f"Unknown tool: {tool_name}")

        try:
            if tool_name == "list_canons":
                structured = self._tool_list_canons(arguments)
            elif tool_name == "submit_batch":
                structured = await self._tool_submit_batch(arguments, params)
            elif tool_name == "job_status":
                structured = await self._tool_job_status(arguments)
            elif tool_name == "get_findings":
                structured = await self._tool_get_findings(arguments)
            elif tool_name == "explain_finding":
                structured = await self._tool_explain_finding(arguments)
            elif tool_name == "propose_fix":
                structured = await self._tool_propose_fix(arguments)
            else:
                raise McpProtocolError(-32602, f"Unknown tool: {tool_name}")
        except McpToolError as tool_err:
            return self._tool_error_result(tool_err.message)
        except Exception as exc:
            return self._tool_error_result(f"Tool {tool_name!r} failed: {exc}")

        return self._format_tool_success(structured)

    def _tool_list_canons(self, args: dict[str, Any]) -> dict[str, Any]:
        cur = PageCursor.decode(args.get("cursor"), expected_scope="list_canons")
        limit = max(1, min(20, int(args.get("limit", 10))))

        all_ids = sorted(_list_canon_ids_lazy())
        items: list[dict[str, Any]] = []
        for cid in all_ids:
            c = _get_canon_lazy(cid)
            items.append(
                {
                    "id": c.id,
                    "version": c.version,
                    "hash": c.hash[:16],
                    "counts": {
                        "terminology": len(c.terminology),
                        "palette": len(c.palette),
                        "facts": len(c.facts),
                        "triggers": len(c.trigger_obligations),
                        "logos": len(c.logos),
                        "voice_profile": c.voice_profile is not None,
                    },
                    "total_rules": len(c),
                }
            )

        page, next_cursor = _pack_paginated_items(
            items,
            offset=cur.offset,
            scope="list_canons",
            max_items_cap=limit,
            envelope_builder=lambda p, nxt: {
                "total_canons": len(items),
                "canons": p,
                "next_cursor": nxt,
            },
        )
        out: dict[str, Any] = {
            "total_canons": len(items),
            "canons": page,
        }
        if next_cursor:
            out["next_cursor"] = next_cursor
            out["nextCursor"] = next_cursor
        return out

    async def _tool_submit_batch(
        self, args: dict[str, Any], raw_params: dict[str, Any]
    ) -> dict[str, Any]:
        canon_id = str(args.get("canon_id") or "").strip()
        if not canon_id:
            raise McpToolError("Parameter `canon_id` is required (e.g. 'indian-digital-lending').")
        try:
            _get_canon_lazy(canon_id)
        except Exception as exc:
            raise McpToolError(
                f"Canon {canon_id!r} not found. Call `list_canons` to see valid Canon IDs."
            ) from exc

        paths = args.get("paths") or []
        inline_items = args.get("items") or []
        if not isinstance(paths, list) or not isinstance(inline_items, list):
            raise McpToolError("Parameters `paths` and `items` must be arrays.")
        if not paths and not inline_items:
            raise McpToolError(
                "Provide at least one file/directory/glob in `paths` or an entry in `items`."
            )

        alpha = float(args.get("alpha", 0.10))
        wait_ms = max(0, min(10000, int(args.get("wait_ms", 1500))))

        try:
            job = await self._batch_manager.submit_batch(
                canon_id=canon_id,
                paths=paths,
                inline_items=inline_items,
                alpha=alpha,
                persist=True,
                wait_for_completion=(wait_ms > 0),
                wait_timeout_s=wait_ms / 1000.0,
            )
        except ValueError as val_err:
            raise McpToolError(str(val_err)) from val_err

        return self._build_job_status_page(job, cursor_token=None, raw_params=raw_params)

    async def _tool_job_status(self, args: dict[str, Any]) -> dict[str, Any]:
        job_id = str(args.get("job_id") or "").strip()
        if not job_id:
            raise McpToolError("Parameter `job_id` is required.")
        job = self._batch_manager.get_job(job_id)
        if job is None:
            raise McpToolError(
                f"Batch job {job_id!r} not found or expired. Submit a new batch via `submit_batch`."
            )
        wait_ms = max(0, min(5000, int(args.get("wait_ms", 150))))
        if not job.is_terminal and wait_ms > 0:
            await job.wait(timeout=wait_ms / 1000.0)
        return self._build_job_status_page(job, cursor_token=args.get("cursor"))

    def _build_job_status_page(
        self,
        job: BatchJob,
        *,
        cursor_token: str | None,
        raw_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scope = f"job:{job.job_id}"
        cur = PageCursor.decode(cursor_token, expected_scope=scope)
        compact_outcomes = [o.to_compact_dict() for o in job.outcomes]

        base_summary = job.summary_dict()
        base_summary["taskId"] = job.job_id
        base_summary["pollIntervalMs"] = 250 if not job.is_terminal else 0
        base_summary["ttlMs"] = 3600000

        page, next_cursor = _pack_paginated_items(
            compact_outcomes,
            offset=cur.offset,
            scope=scope,
            max_items_cap=6,
            envelope_builder=lambda p, nxt: {
                **base_summary,
                "assets": p,
                "next_cursor": nxt,
                "nextCursor": nxt,
            },
        )
        result: dict[str, Any] = {
            **base_summary,
            "assets": page,
        }
        if next_cursor:
            result["next_cursor"] = next_cursor
            result["nextCursor"] = next_cursor
        return result

    async def _tool_get_findings(self, args: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_db()
        job_id = str(args.get("job_id") or "").strip()
        sub_id_raw = args.get("submission_id")
        verdict_filter = str(args.get("verdict") or "all").strip().lower()
        check_filter = str(args.get("check_id") or "").strip()

        if not job_id and sub_id_raw is None:
            raise McpToolError("Provide either `job_id` or `submission_id` to list findings.")

        scope_raw = f"gf:{job_id}:{sub_id_raw}:{verdict_filter}:{check_filter}"
        scope = hashlib.sha256(scope_raw.encode("utf-8")).hexdigest()[:12]
        cur = PageCursor.decode(args.get("cursor"), expected_scope=scope)

        finding_items: list[dict[str, Any]] = []

        if job_id:
            job = self._batch_manager.get_job(job_id)
            if job is None:
                raise McpToolError(f"Batch job {job_id!r} not found.")
            for outcome in job.outcomes:
                for f_idx, f in enumerate(outcome.findings):
                    if verdict_filter == "blocker" and not f.is_blocker:
                        continue
                    if verdict_filter == "warning" and not f.is_warning:
                        continue
                    if check_filter and f.check_id != check_filter:
                        continue
                    row_id = (
                        outcome.finding_row_ids[f_idx]
                        if f_idx < len(outcome.finding_row_ids)
                        else None
                    )
                    finding_items.append(
                        self._compact_finding_item(
                            f,
                            submission_id=outcome.submission_id,
                            row_id=row_id,
                            asset_title=outcome.title,
                        )
                    )
        else:
            sub_id = int(sub_id_raw)  # type: ignore[arg-type]
            async with async_session() as session:
                sub = await repos.get_submission(session, sub_id)
                if sub is None:
                    raise McpToolError(f"Submission #{sub_id} not found.")
                rows = await repos.get_findings_for_submission(session, sub_id)
                for r in rows:
                    f = Finding.model_validate_json(r.payload_json)
                    if verdict_filter == "blocker" and not f.is_blocker:
                        continue
                    if verdict_filter == "warning" and not f.is_warning:
                        continue
                    if check_filter and f.check_id != check_filter:
                        continue
                    finding_items.append(
                        self._compact_finding_item(
                            f,
                            submission_id=sub.id,
                            row_id=r.id,
                            asset_title=sub.title,
                            resolution=r.resolution,
                        )
                    )

        blocker_total = sum(1 for item in finding_items if item["verdict"] == "BLOCKER")
        warning_total = sum(1 for item in finding_items if item["verdict"] == "WARNING")

        header_meta = {
            "job_id": job_id or None,
            "submission_id": int(sub_id_raw) if sub_id_raw is not None else None,
            "total_matching_findings": len(finding_items),
            "blocker_count": blocker_total,
            "warning_count": warning_total,
        }

        page, next_cursor = _pack_paginated_items(
            finding_items,
            offset=cur.offset,
            scope=scope,
            max_items_cap=6,
            envelope_builder=lambda p, nxt: {
                **header_meta,
                "findings": p,
                "next_cursor": nxt,
                "nextCursor": nxt,
            },
        )
        out: dict[str, Any] = {
            **header_meta,
            "findings": page,
        }
        if next_cursor:
            out["next_cursor"] = next_cursor
            out["nextCursor"] = next_cursor
        return out

    @staticmethod
    def _compact_finding_item(
        f: Finding,
        *,
        submission_id: int | None,
        row_id: int | None,
        asset_title: str,
        resolution: str = "open",
    ) -> dict[str, Any]:
        loc_dict = f.locator.model_dump()
        loc_str = (
            f"Span[{loc_dict['start']}, {loc_dict['end']}]"
            if "start" in loc_dict
            else f"BBox[{loc_dict['x']}, {loc_dict['y']}, {loc_dict['w']}, {loc_dict['h']}]"
        )
        item: dict[str, Any] = {
            "finding_id": str(f.id),
            "check_id": f.check_id,
            "severity": f.severity,
            "verdict": "BLOCKER" if f.is_blocker else "WARNING",
            "rule_id": f.rule_ref.rule_id,
            "locator": loc_str,
            "message": f.message[:110],
            "tier": str(f.trace.tier),
            "resolution": resolution,
        }
        if row_id is not None:
            item["row_id"] = row_id
        if submission_id is not None:
            item["submission_id"] = submission_id
        if asset_title:
            item["asset"] = asset_title[:36]
        return item

    async def _resolve_target_finding(
        self, args: dict[str, Any]
    ) -> tuple[int | None, int | None, str, str, Finding]:
        await self._ensure_db()
        row_id = args.get("row_id")
        sub_id = args.get("submission_id")
        finding_id = str(args.get("finding_id") or "").strip()
        job_id = str(args.get("job_id") or "").strip()

        if row_id is not None:
            async with async_session() as session:
                row = await repos.get_finding_by_row_id(session, int(row_id))
                if row is not None:
                    sub = await repos.get_submission(session, row.submission_id)
                    if sub is not None:
                        return (
                            sub.id,
                            row.id,
                            sub.canon_id,
                            sub.raw_content,
                            Finding.model_validate_json(row.payload_json),
                        )

        if sub_id is not None:
            async with async_session() as session:
                sub = await repos.get_submission(session, int(sub_id))
                if sub is None:
                    raise McpToolError(f"Submission #{sub_id} not found.")
                rows = await repos.get_findings_for_submission(session, sub.id)
                for r in rows:
                    if not finding_id or r.finding_id == finding_id:
                        return (
                            sub.id,
                            r.id,
                            sub.canon_id,
                            sub.raw_content,
                            Finding.model_validate_json(r.payload_json),
                        )

        if job_id:
            job = self._batch_manager.get_job(job_id)
            if job is None:
                raise McpToolError(f"Batch job {job_id!r} not found.")
            for outcome in job.outcomes:
                for idx, f in enumerate(outcome.findings):
                    r_id = (
                        outcome.finding_row_ids[idx] if idx < len(outcome.finding_row_ids) else None
                    )
                    if (
                        (row_id is not None and r_id == int(row_id))
                        or (finding_id and str(f.id) == finding_id)
                        or (row_id is None and not finding_id)
                    ):
                        raw_c = ""
                        if outcome.submission_id is not None:
                            async with async_session() as session:
                                sub = await repos.get_submission(session, outcome.submission_id)
                                if sub is not None:
                                    raw_c = sub.raw_content
                        return (
                            outcome.submission_id,
                            r_id,
                            job.canon_id,
                            raw_c,
                            f,
                        )

        if finding_id:
            async with async_session() as session:
                subs = await repos.list_submissions(session, limit=50)
                for s in subs:
                    rows = await repos.get_findings_for_submission(session, s.id)
                    for r in rows:
                        if r.finding_id == finding_id:
                            return (
                                s.id,
                                r.id,
                                s.canon_id,
                                s.raw_content,
                                Finding.model_validate_json(r.payload_json),
                            )

        raise McpToolError(
            "Finding not found. Provide a valid `row_id`, `finding_id`, or `submission_id` "
            "from `get_findings`."
        )

    async def _tool_explain_finding(self, args: dict[str, Any]) -> dict[str, Any]:
        sub_id, row_id, canon_id, raw_content, f = await self._resolve_target_finding(args)

        flagged_excerpt = ""
        node_path = ""
        if raw_content:
            ast = parse_raw_bundle_ast(raw_content)
            for node in ast:
                if str(node.id) == str(f.node_id):
                    node_path = node.path
                    if isinstance(node, TextNode):
                        loc = f.locator.model_dump()
                        if "start" in loc and "end" in loc:
                            s, e = int(loc["start"]), int(loc["end"])
                            flagged_excerpt = node.text[max(0, s) : min(len(node.text), e)][:180]
                        else:
                            flagged_excerpt = node.text[:180]
                    break

        ev_dict = f.evidence.model_dump()
        sug_dict = f.suggestion.model_dump() if f.suggestion is not None else None

        explanation: dict[str, Any] = {
            "finding_id": str(f.id),
            "row_id": row_id,
            "submission_id": sub_id,
            "canon_id": canon_id,
            "check_id": f.check_id,
            "severity": f.severity,
            "verdict": "BLOCKER" if f.is_blocker else "WARNING",
            "node_id": str(f.node_id)[:24],
            "node_path": node_path,
            "locator": f.locator.model_dump(),
            "flagged_excerpt": flagged_excerpt,
            "message": f.message[:240],
            "rule_ref": {
                "rule_id": f.rule_ref.rule_id,
                "rule_type": f.rule_ref.rule_type,
                "source_text": f.rule_ref.source_text[:200],
            },
            "evidence": ev_dict,
            "suggestion": sug_dict,
            "trace": f.trace.model_dump(),
            "governance_permissions": (
                "BLOCKER (S >= 50): Locked against override/dismissal; requires surgical fix or "
                "Reviewer sign-off in Review Studio after expanding SlotDiff."
                if f.is_blocker
                else "WARNING (S < 50): Creator may accept fix or deliberately override with a "
                "recorded justification reason (>= 3 chars) in Review Studio."
            ),
        }
        if sub_id is not None:
            explanation["studio_url"] = f"/#/submissions/{sub_id}"
        return explanation

    async def _tool_propose_fix(self, args: dict[str, Any]) -> dict[str, Any]:
        sub_id, row_id, canon_id, raw_content, f = await self._resolve_target_finding(args)
        canon = _get_canon_lazy(canon_id)

        target_node: TextNode | None = None
        if raw_content:
            ast = parse_raw_bundle_ast(raw_content)
            target_node = next(
                (
                    n
                    for n in ast.of_kind(NodeKind.TEXT)
                    if isinstance(n, TextNode) and str(n.id) == str(f.node_id)
                ),
                None,
            )
            if target_node is None:
                text_nodes = [n for n in ast.of_kind(NodeKind.TEXT) if isinstance(n, TextNode)]
                if text_nodes:
                    target_node = text_nodes[0]

        if target_node is not None:
            rewrite_res = await default_constrained_rewriter.rewrite(
                target_node,
                f,
                canon,
                verify_fn=run_checks_collect,
            )
            return {
                "finding_id": str(f.id),
                "row_id": row_id,
                "submission_id": sub_id,
                "check_id": f.check_id,
                "mode": "tier3_surgical_rewrite",
                "original_text": rewrite_res.original_text[:280],
                "proposed_text": rewrite_res.rewritten_text[:320],
                "edit_distance_ratio": rewrite_res.edit_distance_ratio,
                "max_edit_distance_ratio": rewrite_res.max_edit_distance_ratio,
                "reverified_tier1_tier2": rewrite_res.reverified,
                "remaining_findings_count": rewrite_res.remaining_findings_count,
                "pii_masked_count": rewrite_res.pii_masked_count,
                "used_provider": rewrite_res.used_provider,
                "api_key_configured": rewrite_res.api_key_configured,
                "provider_notice": rewrite_res.provider_notice[:240],
                "quality_gates_passed": rewrite_res.quality_gates.get("all_passed", True),
                "suggestion": rewrite_res.suggestion.model_dump(),
                "studio_url": f"/#/submissions/{sub_id}" if sub_id is not None else None,
                "human_oversight_note": ("Preview only: apply and sign off in the Review Studio."),
            }

        ev_dict = f.evidence.model_dump()
        return {
            "finding_id": str(f.id),
            "row_id": row_id,
            "submission_id": sub_id,
            "check_id": f.check_id,
            "mode": "deterministic_visual_repair",
            "message": f.message[:220],
            "evidence": ev_dict,
            "suggestion": f.suggestion.model_dump() if f.suggestion else None,
            "reverified_tier1_tier2": True,
            "studio_url": f"/#/submissions/{sub_id}" if sub_id is not None else None,
            "human_oversight_note": (
                "Visual alternative preview: inspect and sign off in the Review Studio."
            ),
        }

    async def _handle_tasks_get(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = str(params.get("taskId") or params.get("job_id") or "").strip()
        if not task_id:
            raise McpProtocolError(-32602, "Missing required parameter: taskId")
        job = self._batch_manager.get_job(task_id)
        if job is None:
            raise McpProtocolError(-32602, f"Unknown taskId: {task_id}")
        if not job.is_terminal:
            await job.wait(timeout=0.15)
        status_payload = self._build_job_status_page(job, cursor_token=params.get("cursor"))
        out: dict[str, Any] = {
            "taskId": job.job_id,
            "status": job.status,
            "pollIntervalMs": 250 if not job.is_terminal else 0,
            "ttlMs": 3600000,
        }
        if job.is_terminal:
            out["result"] = self._format_tool_success(status_payload)
        else:
            out["progress"] = {
                "processed": job.processed_items,
                "total": len(job.inputs),
                "ratio": job.progress_ratio,
            }
        return out

    def _handle_tasks_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = str(params.get("taskId") or params.get("job_id") or "").strip()
        if not task_id:
            raise McpProtocolError(-32602, "Missing required parameter: taskId")
        job = self._batch_manager.get_job(task_id)
        if job is None:
            raise McpProtocolError(-32602, f"Unknown taskId: {task_id}")
        job.request_cancel()
        return {"taskId": job.job_id, "status": job.status}

    def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        resources = [
            {
                "uri": f"canongate://canons/{cid}",
                "name": f"Canon: {cid}",
                "description": f"Signed CanonGate rulebook '{cid}'",
                "mimeType": "application/json",
            }
            for cid in sorted(_list_canon_ids_lazy())
        ]
        return {"resultType": "complete", "resources": resources[:10]}

    async def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = str(params.get("uri") or "").strip()
        if uri.startswith("canongate://canons/"):
            cid = uri.removeprefix("canongate://canons/").strip("/")
            try:
                c = _get_canon_lazy(cid)
            except Exception as exc:
                raise McpProtocolError(-32602, f"Resource not found: {uri}") from exc
            summary = {
                "id": c.id,
                "version": c.version,
                "hash": c.hash,
                "terminology_count": len(c.terminology),
                "palette_count": len(c.palette),
                "facts_count": len(c.facts),
                "trigger_obligations_count": len(c.trigger_obligations),
                "logos_count": len(c.logos),
            }
            return {
                "resultType": "complete",
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": _compact_json(summary),
                    }
                ],
            }
        raise McpProtocolError(-32602, f"Unsupported resource URI: {uri}")

    @staticmethod
    def _tool_error_result(message: str) -> dict[str, Any]:
        err_obj = {"error": message[:1200], "isError": True}
        return {
            "resultType": "complete",
            "content": [{"type": "text", "text": _compact_json(err_obj)}],
            "structuredContent": err_obj,
            "isError": True,
        }

    @classmethod
    def _format_tool_success(cls, structured: dict[str, Any]) -> dict[str, Any]:
        trimmed = cls._trim_structured_to_budget(structured, _MAX_STRUCTURED_PAYLOAD_BYTES)
        text_json = _compact_json(trimmed)
        return {
            "resultType": "complete",
            "content": [{"type": "text", "text": text_json}],
            "structuredContent": trimmed,
            "isError": False,
        }

    @staticmethod
    def _trim_structured_to_budget(data: dict[str, Any], max_bytes: int) -> dict[str, Any]:
        if _byte_len(_compact_json(data)) <= max_bytes:
            return data
        copy_data = dict(data)
        for list_key in ("findings", "assets", "canons"):
            if isinstance(copy_data.get(list_key), list):
                items = list(copy_data[list_key])
                while (
                    len(items) > 1
                    and _byte_len(_compact_json({**copy_data, list_key: items})) > max_bytes
                ):
                    items.pop()
                copy_data[list_key] = items
        for str_key in ("proposed_text", "original_text", "flagged_excerpt", "message"):
            if (
                isinstance(copy_data.get(str_key), str)
                and _byte_len(_compact_json(copy_data)) > max_bytes
            ):
                copy_data[str_key] = copy_data[str_key][:120] + "…"
        return copy_data

    @staticmethod
    def _enforce_wire_budget(response: dict[str, Any]) -> dict[str, Any]:
        raw = _compact_json(response)
        if _byte_len(raw) <= MAX_MCP_WIRE_BYTES:
            return response
        result = response.get("result")
        if isinstance(result, dict) and "structuredContent" in result:
            sc = result["structuredContent"]
            result["content"] = [
                {
                    "type": "text",
                    "text": _compact_json(
                        {
                            "summary": "See structuredContent for full paginated payload (<4KB).",
                            "keys": list(sc.keys()) if isinstance(sc, dict) else [],
                        }
                    ),
                }
            ]
        return response

    @staticmethod
    def _error_frame(
        req_id: Any,
        code: int,
        message: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": err}


default_mcp_server = CanonGateMcpServer()


async def run_stdio_server_async(
    server: CanonGateMcpServer | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Run the MCP server over newline-delimited `stdio` (`stdin` -> `stdout`, logs -> `stderr`)."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="[canongate-mcp] %(levelname)s: %(message)s",
    )
    active_server = server or default_mcp_server
    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout

    line_queue: asyncio.Queue[str] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _stdin_reader() -> None:
        try:
            while True:
                raw_line = in_stream.readline()
                loop.call_soon_threadsafe(line_queue.put_nowait, raw_line)
                if not raw_line:
                    break
        except Exception:
            loop.call_soon_threadsafe(line_queue.put_nowait, "")

    import threading

    reader_thread = threading.Thread(
        target=_stdin_reader,
        name="canongate-mcp-stdin",
        daemon=True,
    )
    reader_thread.start()

    while True:
        line = await line_queue.get()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue

        try:
            msg = json.loads(stripped)
        except json.JSONDecodeError as exc:
            err_resp = active_server._error_frame(None, -32700, f"Parse error: {exc}")
            out_stream.write(_compact_json(err_resp) + "\n")
            out_stream.flush()
            continue

        resp = await active_server.handle_jsonrpc(msg)
        if resp is not None:
            wire_line = _compact_json(resp)
            out_stream.write(wire_line + "\n")
            out_stream.flush()

    return 0


def run_stdio_server(
    server: CanonGateMcpServer | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Synchronous entry point for `canongate mcp` / `canongate-mcp`."""
    return asyncio.run(run_stdio_server_async(server, stdin=stdin, stdout=stdout))


def main() -> int:
    return run_stdio_server()


if __name__ == "__main__":
    raise SystemExit(main())
