"""Pre-Publish Webhook Gate (`POST /api/gate/check`) & MCP Endpoint (`POST /api/mcp`).

Implements Round 2 §5.1 (`canongate-mcp + gate`):
1. **`POST /api/gate/check`:**
   - Audits campaign bundles or CMS webhook payloads against an active `Canon` and
     Conformal Risk Control level `alpha`, returning a deterministic pre-publish
     verdict (`allow | needs_review | block`):
     - `allow`: 0 Blockers and 0 Warnings.
     - `needs_review`: 0 Blockers and >= 1 Warning.
     - `block`: >= 1 Blocker (`severity >= 50`).
   - Built-in CMS Adapters:
     - **Generic / Native CanonGate Bundle:** `title`, `raw_content`, `image_paths`, `attachments`.
     - **Shopify Webhook Adapter (`adapter="shopify"` or auto-detected):** Extracts product
       `title`, `body_html`, `vendor`, `tags`, `variants[].{price, compare_at_price, sku}`,
       and `images[].{src, alt}` into an HTML + Markdown table bundle.
     - **Webflow Webhook Adapter (`adapter="webflow"` or auto-detected):** Extracts CMS
       item/page `fieldData` (`name`, `post-body`, `summary`, `cta-text`,
       `hero-image` / `main-image`) into a unified multimodal bundle.
2. **`POST /api/mcp` (MCP `2026-07-28` Streamable HTTP Transport):**
   - Validates `Origin` header to prevent DNS rebinding (`403 Forbidden` on untrusted origin).
   - Validates `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` headers (including
     `=?base64?...?=` RFC 9110 sentinel decoding), returning `400 Bad Request` with
     JSON-RPC error `-32020 HeaderMismatch` on mismatch.
   - Returns `405 Method Not Allowed` on `GET /api/mcp` and `DELETE /api/mcp` per MCP `2026-07-28`.
"""

from __future__ import annotations

import base64
import re
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from canongate.api.deps import SessionDep, get_canon
from canongate.api.routes.submissions import (
    BundleAttachmentDto,
    _ApiDto,
    _ingest_bundle_attachments,
    _parse_submission_ast,
)
from canongate.domain.ast import ImageNode, TextNode
from canongate.domain.types import content_hash
from canongate.engine.conformal import default_calibrator
from canongate.engine.runner import run_checks_collect
from canongate.mcp.server import (
    SUPPORTED_PROTOCOL_VERSIONS,
    TOOL_MAP,
    default_mcp_server,
)
from canongate.parsers.html import parse_html
from canongate.store import repos

router = APIRouter(tags=["gate", "mcp"])

_TRUSTED_HOSTS: frozenset[str] = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "testserver",
        "canongate-web.onrender.com",
        "canongate-api.onrender.com",
        "meerpi.github.io",
    }
)

_B64_SENTINEL_RE = re.compile(r"^=\?base64\?([A-Za-z0-9+/=]+)\?=$")


def _decode_mcp_header_value(raw_val: str) -> str:
    """Decode an MCP `2026-07-28` header value (supporting `=?base64?...?=` sentinel encoding)."""
    m = _B64_SENTINEL_RE.match(raw_val)
    if m is not None:
        try:
            return base64.b64decode(m.group(1).encode("ascii")).decode("utf-8")
        except Exception as exc:
            raise ValueError(f"Invalid base64 sentinel header value: {raw_val!r}") from exc
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_val):
        raise ValueError("Header value contains forbidden control characters")
    return raw_val


def _is_trusted_origin(origin: str | None) -> bool:
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        if host in _TRUSTED_HOSTS:
            return True
        return host.endswith((".onrender.com", ".github.io", ".loca.lt"))
    except Exception:
        return False


class GateFindingItemDto(_ApiDto):
    finding_id: str
    row_id: int | None = None
    check_id: str
    node_id: str
    severity: int
    verdict: Literal["BLOCKER", "WARNING"]
    rule_id: str
    locator: dict[str, Any]
    message: str
    suggestion_label: str | None = None
    replacement_preview: str | None = None
    tier: str


class GateCheckRequest(BaseModel):
    canon_id: str = "acme-corp"
    adapter: Literal["auto", "generic", "shopify", "webflow"] = "auto"
    title: str = ""
    raw_content: str = ""
    image_paths: list[str] = Field(default_factory=list)
    attachments: list[BundleAttachmentDto] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    webhook_payload: dict[str, Any] = Field(default_factory=dict)
    alpha: float = 0.10
    persist: bool = True
    strict_http_status: bool = False


class GateCheckResponse(_ApiDto):
    decision: Literal["allow", "needs_review", "block"]
    adapter_used: str
    canon_id: str
    canon_version: str
    canon_hash: str
    content_hash: str
    submission_id: int | None = None
    studio_url: str | None = None
    alpha: float
    conformal_threshold: float
    blocker_count: int
    warning_count: int
    total_findings: int
    latency_ms: float
    findings: list[GateFindingItemDto] = Field(default_factory=list)


def _normalize_shopify_payload(data: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Normalize a Shopify `products/*` or `pages/*` payload into `(title, content, images)`."""
    product = data.get("product") if isinstance(data.get("product"), dict) else data
    title = str(product.get("title") or "Shopify Product").strip()
    vendor = str(product.get("vendor") or "").strip()
    body_html = str(product.get("body_html") or product.get("body") or "").strip()
    tags = str(product.get("tags") or "").strip()

    blocks: list[str] = []
    header_line = f"{title} ({vendor})" if vendor else title
    if header_line:
        blocks.append(header_line)
    if tags:
        blocks.append(f"Tags: {tags}")

    if body_html:
        html_ast = parse_html(body_html, source="shopify_html")
        for node in html_ast:
            if isinstance(node, TextNode) and node.text.strip():
                if "/hidden[" in node.path:
                    blocks.append(f"[HIDDEN_BLOCK] {node.text.strip()}")
                else:
                    blocks.append(node.text.strip())
            elif (
                isinstance(node, ImageNode)
                and node.alt == ""
                and not Path(node.asset_path).is_file()
            ):
                blocks.append(f"[HTML_IMG_MISSING_ALT] {node.asset_path}")

    variants = product.get("variants")
    if isinstance(variants, list) and variants:
        v_lines = [
            "| SKU / Variant | Price | Compare At Price |",
            "| --- | --- | --- |",
        ]
        has_rows = False
        for idx, v in enumerate(variants):
            if not isinstance(v, dict):
                continue
            v_title = str(v.get("title") or v.get("sku") or f"Variant {idx + 1}").strip()
            price = str(v.get("price") or "").strip()
            comp = str(v.get("compare_at_price") or "").strip()
            if price or comp:
                has_rows = True
                v_lines.append(f"| {v_title} | {price or '—'} | {comp or '—'} |")
        if has_rows:
            blocks.append("\n".join(v_lines))

    img_paths: list[str] = []
    images = product.get("images")
    if isinstance(images, list):
        for idx, img in enumerate(images):
            if not isinstance(img, dict):
                continue
            src = str(img.get("src") or img.get("path") or f"shopify_img_{idx}").strip()
            alt = img.get("alt")
            alt_clean = str(alt).strip() if alt is not None else ""
            if src and Path(src).is_file():
                img_paths.append(src)
            if not alt_clean:
                blocks.append(f"[HTML_IMG_MISSING_ALT] {src}")

    return title, "\n\n".join(blocks), img_paths


def _normalize_webflow_payload(data: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Normalize a Webflow CMS `item_*` or `page_*` payload into `(title, content, images)`."""
    inner = data.get("payload") if isinstance(data.get("payload"), dict) else data
    fields = inner.get("fieldData") if isinstance(inner.get("fieldData"), dict) else inner

    title = str(
        fields.get("name") or fields.get("title") or inner.get("title") or "Webflow CMS Item"
    ).strip()

    blocks: list[str] = [title] if title else []
    for text_key in (
        "summary",
        "post-summary",
        "description",
        "cta-text",
        "disclaimer",
        "footnote",
    ):
        val = fields.get(text_key)
        if isinstance(val, str) and val.strip():
            blocks.append(val.strip())

    html_body = str(
        fields.get("post-body")
        or fields.get("body")
        or fields.get("rich-text")
        or inner.get("body")
        or ""
    ).strip()
    if html_body:
        if "<" in html_body and ">" in html_body:
            html_ast = parse_html(html_body, source="webflow_html")
            for node in html_ast:
                if isinstance(node, TextNode) and node.text.strip():
                    if "/hidden[" in node.path:
                        blocks.append(f"[HIDDEN_BLOCK] {node.text.strip()}")
                    else:
                        blocks.append(node.text.strip())
                elif isinstance(node, ImageNode) and node.alt == "":
                    blocks.append(f"[HTML_IMG_MISSING_ALT] {node.asset_path}")
        else:
            blocks.append(html_body)

    img_paths: list[str] = []
    for img_key in ("main-image", "hero-image", "banner-image", "thumbnail"):
        img_obj = fields.get(img_key)
        if isinstance(img_obj, dict):
            url = str(img_obj.get("url") or img_obj.get("fileId") or img_key).strip()
            alt = img_obj.get("alt")
            alt_clean = str(alt).strip() if alt is not None else ""
            if url and Path(url).is_file():
                img_paths.append(url)
            if not alt_clean:
                blocks.append(f"[HTML_IMG_MISSING_ALT] {url}")

    return title, "\n\n".join(blocks), img_paths


def _detect_and_normalize_gate_request(
    req: GateCheckRequest,
) -> tuple[str, str, str, list[str]]:
    payload = req.payload or req.webhook_payload or {}
    adapter = req.adapter

    if adapter == "auto":
        if (
            "body_html" in payload
            or "variants" in payload
            or isinstance(payload.get("product"), dict)
        ):
            adapter = "shopify"
        elif (
            "fieldData" in payload
            or "triggerType" in payload
            or (isinstance(payload.get("payload"), dict) and "fieldData" in payload["payload"])
        ):
            adapter = "webflow"
        else:
            adapter = "generic"

    if adapter == "shopify":
        s_title, s_content, s_imgs = _normalize_shopify_payload(payload)
        merged_title = req.title.strip() or s_title
        merged_content = (
            f"{req.raw_content.strip()}\n\n{s_content}".strip()
            if req.raw_content.strip()
            else s_content
        )
        return "shopify", merged_title, merged_content, [*req.image_paths, *s_imgs]

    if adapter == "webflow":
        w_title, w_content, w_imgs = _normalize_webflow_payload(payload)
        merged_title = req.title.strip() or w_title
        merged_content = (
            f"{req.raw_content.strip()}\n\n{w_content}".strip()
            if req.raw_content.strip()
            else w_content
        )
        return "webflow", merged_title, merged_content, [*req.image_paths, *w_imgs]

    g_title = req.title.strip() or str(payload.get("title") or "Pre-Publish Gate Check").strip()
    g_content = (
        req.raw_content.strip()
        or str(payload.get("raw_content") or payload.get("text") or "").strip()
    )
    g_imgs = list(req.image_paths)
    if isinstance(payload.get("image_paths"), list):
        g_imgs.extend(str(x) for x in payload["image_paths"] if str(x).strip())
    return "generic", g_title, g_content, g_imgs


@router.post("/gate/check", response_model=GateCheckResponse)
async def pre_publish_gate_check(
    req: GateCheckRequest,
    response: Response,
    session: SessionDep,
) -> GateCheckResponse:
    """Synchronous pre-publish webhook gate for Shopify, Webflow, and CI/CD pipelines."""
    t0 = time.perf_counter()
    canon = get_canon(req.canon_id)
    clamped_alpha = max(0.01, min(0.25, round(float(req.alpha), 4)))
    conformal_threshold = default_calibrator.threshold(clamped_alpha)

    adapter_used, title, base_content, base_images = _detect_and_normalize_gate_request(req)
    raw_content, all_images = _ingest_bundle_attachments(base_content, base_images, req.attachments)
    if all_images:
        extra_blocks = [
            f"![Banner]({img_p})" for img_p in all_images if img_p and img_p not in raw_content
        ]
        if extra_blocks:
            suffix = "\n\n".join(extra_blocks)
            raw_content = f"{raw_content.rstrip()}\n\n{suffix}" if raw_content.strip() else suffix

    if not raw_content.strip():
        raise HTTPException(
            status_code=400,
            detail="Gate check payload contains no auditable text or media assets.",
        )

    c_hash = content_hash(raw_content.encode("utf-8"))
    ast = _parse_submission_ast(raw_content)
    raw_findings = await run_checks_collect(ast, canon)
    calibrated = default_calibrator.filter_and_calibrate_findings(raw_findings, alpha=clamped_alpha)

    sub_id: int | None = None
    row_ids: list[int] = []
    if req.persist:
        sub = await repos.create_submission(
            session,
            title=title,
            raw_content=raw_content,
            content_hash=c_hash,
            canon_id=canon.id,
            canon_hash=canon.hash,
            creator_id=1,
        )
        sub_id = sub.id
        await repos.save_findings(session, sub.id, calibrated)
        saved_rows = await repos.get_findings_for_submission(session, sub.id)
        row_ids = [r.id for r in saved_rows]

    blockers = sum(1 for f in calibrated if f.is_blocker)
    warnings = sum(1 for f in calibrated if f.is_warning)
    if blockers > 0:
        decision: Literal["allow", "needs_review", "block"] = "block"
    elif warnings > 0:
        decision = "needs_review"
    else:
        decision = "allow"

    if req.strict_http_status and decision == "block":
        response.status_code = 409

    finding_dtos: list[GateFindingItemDto] = []
    for idx, f in enumerate(calibrated):
        sug_label = f.suggestion.label if f.suggestion is not None else None
        rep_preview = (
            f.suggestion.replacements[0].replacement[:140]
            if (f.suggestion is not None and f.suggestion.replacements)
            else None
        )
        finding_dtos.append(
            GateFindingItemDto(
                finding_id=str(f.id),
                row_id=row_ids[idx] if idx < len(row_ids) else None,
                check_id=f.check_id,
                node_id=str(f.node_id),
                severity=f.severity,
                verdict="BLOCKER" if f.is_blocker else "WARNING",
                rule_id=f.rule_ref.rule_id,
                locator=f.locator.model_dump(),
                message=f.message,
                suggestion_label=sug_label,
                replacement_preview=rep_preview,
                tier=str(f.trace.tier),
            )
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return GateCheckResponse(
        decision=decision,
        adapter_used=adapter_used,
        canon_id=canon.id,
        canon_version=canon.version,
        canon_hash=canon.hash,
        content_hash=c_hash,
        submission_id=sub_id,
        studio_url=f"/#/submissions/{sub_id}" if sub_id is not None else None,
        alpha=clamped_alpha,
        conformal_threshold=conformal_threshold,
        blocker_count=blockers,
        warning_count=warnings,
        total_findings=len(calibrated),
        latency_ms=elapsed_ms,
        findings=finding_dtos,
    )


@router.get("/mcp")
@router.delete("/mcp")
async def mcp_disallowed_methods() -> JSONResponse:
    """Per MCP 2026-07-28 Streamable HTTP spec: GET and DELETE return 405 Method Not Allowed."""
    return JSONResponse(
        status_code=405,
        content={
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32600,
                "message": "Method Not Allowed: MCP 2026-07-28 Streamable HTTP uses POST only.",
            },
        },
    )


@router.post("/mcp")
async def mcp_streamable_http_endpoint(request: Request) -> Response:
    """MCP `2026-07-28` + `2025-03-26` Streamable HTTP endpoint."""
    origin = request.headers.get("origin")
    if not _is_trusted_origin(origin):
        return JSONResponse(
            status_code=403,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": f"Forbidden Origin: {origin}"},
            },
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: invalid JSON body"},
            },
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid JSON-RPC request body"},
            },
        )

    req_id = body.get("id")
    method = str(body.get("method") or "")
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}

    hdr_ver = request.headers.get("mcp-protocol-version")
    if hdr_ver is not None:
        body_ver = meta.get("io.modelcontextprotocol/protocolVersion")
        if isinstance(body_ver, str) and hdr_ver != body_ver:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32020,
                        "message": (
                            f"HeaderMismatch: MCP-Protocol-Version header {hdr_ver!r} "
                            f"does not match body _meta version {body_ver!r}"
                        ),
                    },
                },
            )
        if hdr_ver not in SUPPORTED_PROTOCOL_VERSIONS:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32022,
                        "message": f"UnsupportedProtocolVersionError: {hdr_ver}",
                        "data": {"supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS)},
                    },
                },
            )

    hdr_method = request.headers.get("mcp-method")
    if hdr_method is not None and hdr_method != method:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32020,
                    "message": (
                        f"HeaderMismatch: Mcp-Method header {hdr_method!r} "
                        f"does not match body method {method!r}"
                    ),
                },
            },
        )

    hdr_name_raw = request.headers.get("mcp-name")
    if hdr_name_raw is not None:
        try:
            hdr_name = _decode_mcp_header_value(hdr_name_raw)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32020, "message": f"HeaderMismatch: {exc}"},
                },
            )
        expected_name = str(params.get("name") or params.get("uri") or "")
        if expected_name and hdr_name != expected_name:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32020,
                        "message": (
                            f"HeaderMismatch: Mcp-Name header {hdr_name!r} "
                            f"does not match body target {expected_name!r}"
                        ),
                    },
                },
            )

    if method == "tools/call":
        tool_name = str(params.get("name") or "")
        tool_def = TOOL_MAP.get(tool_name)
        args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if tool_def is not None:
            props = tool_def.get("inputSchema", {}).get("properties", {})
            for prop_key, prop_schema in props.items():
                mcp_hdr_suffix = prop_schema.get("x-mcp-header")
                if not mcp_hdr_suffix:
                    continue
                hdr_key = f"mcp-param-{mcp_hdr_suffix}".lower()
                if hdr_key in request.headers:
                    try:
                        decoded_param = _decode_mcp_header_value(request.headers[hdr_key])
                    except ValueError as exc:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {"code": -32020, "message": f"HeaderMismatch: {exc}"},
                            },
                        )
                    if prop_key not in args or str(args[prop_key]) != decoded_param:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": -32020,
                                    "message": (
                                        f"HeaderMismatch: header Mcp-Param-{mcp_hdr_suffix} "
                                        f"({decoded_param!r}) does not match "
                                        f"body argument {prop_key!r}"
                                    ),
                                },
                            },
                        )

    resp_payload = await default_mcp_server.handle_jsonrpc(body)
    if resp_payload is None:
        return Response(status_code=202)

    err_obj = resp_payload.get("error")
    if isinstance(err_obj, dict):
        code = err_obj.get("code")
        if code == -32601:
            return JSONResponse(status_code=404, content=resp_payload)
        if code in (-32020, -32021, -32022):
            return JSONResponse(status_code=400, content=resp_payload)

    return JSONResponse(
        status_code=200,
        content=resp_payload,
        headers={"X-Accel-Buffering": "no"},
    )
