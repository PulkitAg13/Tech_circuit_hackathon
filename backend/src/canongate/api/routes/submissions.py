"""Submission routes: create, list, get findings, workflow actions, SSE stream,
banner asset serving, Conformal Risk Control (alpha), signed certificates,
immutable version history, inline comment threads, Tier 3 constrained surgical
rewriting, and deterministic replay manifests.
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

try:
    from sse_starlette.sse import EventSourceResponse
except ImportError:

    class EventSourceResponse(StreamingResponse):  # type: ignore[no-redef]
        def __init__(self, content: Any, **kwargs: Any) -> None:
            kwargs.setdefault("media_type", "text/event-stream")
            super().__init__(content, **kwargs)
            self.body_iterator = content

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            orig_iter = self.body_iterator

            async def _sse_bytes() -> AsyncIterator[bytes]:
                async for item in orig_iter:
                    if isinstance(item, dict):
                        ev = item.get("event", "message")
                        data = item.get("data", "")
                        yield f"event: {ev}\ndata: {data}\n\n".encode()
                    elif isinstance(item, str):
                        yield item.encode("utf-8")
                    elif isinstance(item, bytes):
                        yield item

            self.body_iterator = _sse_bytes()
            await super().__call__(scope, receive, send)


from canongate.api.deps import CurrentUser, SessionDep, get_canon
from canongate.domain.ast import ContentAST, ImageNode, Node, NodeKind, TextNode
from canongate.domain.finding import Finding
from canongate.domain.types import content_hash
from canongate.domain.workflow import (
    Action,
    ResolutionError,
    Role,
    Status,
    TransitionError,
    next_status,
    validate_resolution,
)
from canongate.engine.check import Check
from canongate.engine.conformal import default_calibrator
from canongate.engine.rewriter import default_constrained_rewriter
from canongate.engine.runner import run_checks, run_checks_collect
from canongate.ledger.c2pa_outbound import build_governance_manifest, sign_approved_asset
from canongate.ledger.certificate import GovernanceCertificate, derive_audit_signing_key
from canongate.ledger.chain import GENESIS_HASH, compute_event_hash
from canongate.ledger.merkle import MerkleTree
from canongate.parsers.bundle import default_bundle_parser
from canongate.parsers.tables import parse_markdown_text
from canongate.parsers.text import parse_text
from canongate.store import repos

router = APIRouter(prefix="/submissions", tags=["submissions"])


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_UPLOAD_DIR = Path(".canongate_uploads")


class _ApiDto(BaseModel):
    """Pydantic v1/v2 compatible DTO base with `.model_dump(mode="json")` support."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.pop("mode", None)
        if hasattr(super(), "model_dump"):
            return super().model_dump(**kwargs)
        return json.loads(self.json(**kwargs))


# ── Request / Response models ────────────────────────────────────────


class BundleAttachmentDto(_ApiDto):
    filename: str
    content_base64: str


class CreateSubmissionRequest(_ApiDto):
    title: str = "Untitled"
    raw_content: str = ""
    canon_id: str
    image_paths: list[str] = []
    attachments: list[BundleAttachmentDto] = []


class UpdateSubmissionContentRequest(_ApiDto):
    raw_content: str
    change_note: str = "Edited campaign copy in Review Studio"
    alpha: float = 0.10


class ImageNodeMetaDto(_ApiDto):
    index: int
    node_id: str
    asset_path: str
    width: int
    height: int
    alt: str | None = None
    url: str


class SubmissionResponse(_ApiDto):
    id: int
    title: str
    status: str
    content_hash: str
    canon_id: str
    canon_hash: str
    creator_id: int
    created_at: str
    updated_at: str
    raw_content: str = ""
    paragraph_node_ids: list[str] = []
    text_blocks: list[str] = []
    image_paths: list[str] = []
    image_nodes: list[ImageNodeMetaDto] = []


class WorkflowActionRequest(_ApiDto):
    action: str
    comment: str = ""


class FindingResolutionRequest(_ApiDto):
    resolution: str  # accepted | dismissed | overridden
    apply_suggestion: bool = True
    reason: str | None = None


class FindingResponse(_ApiDto):
    row_id: int
    finding_id: str
    check_id: str
    node_id: str
    severity: int
    message: str
    resolution: str
    resolution_reason: str = ""
    payload: dict


class SubmissionVersionResponse(_ApiDto):
    version_number: int
    content_hash: str
    canon_hash: str
    raw_content: str
    created_by: int
    change_note: str = ""
    created_at: str


class CreateCommentRequest(_ApiDto):
    finding_id: int | None = None
    body: str


class SubmissionCommentResponse(_ApiDto):
    id: int
    submission_id: int
    finding_id: int | None = None
    author_id: int
    author_name: str
    role: str
    body: str
    created_at: str


class SurgicalRewriteResponse(_ApiDto):
    row_id: int
    finding_id: str
    original_text: str
    rewritten_text: str
    edit_distance_ratio: float
    max_edit_distance_ratio: float
    reverified: bool
    remaining_findings_count: int
    pii_masked_count: int
    masked_prompt_preview: str
    used_provider: str
    api_key_configured: bool = False
    provider_notice: str = ""
    quality_gates: dict[str, Any] = {}
    context_trace: dict[str, Any] = {}
    suggestion: dict[str, Any]


def _ingest_bundle_attachments(
    raw_content: str,
    image_paths: list[str],
    attachments: list[BundleAttachmentDto],
    *,
    upload_dir: Path | None = None,
) -> tuple[str, list[str]]:
    """Parse uploaded `.docx`, `.pdf`, `.html`, `.md`, `.png`, `.jpg` attachments
    via BundleParser.
    """
    if not attachments:
        return raw_content, list(image_paths)

    target_dir = upload_dir or _UPLOAD_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    text_blocks: list[str] = [raw_content.strip()] if raw_content.strip() else []
    merged_images: list[str] = list(image_paths)

    for att in attachments:
        try:
            raw_bytes = base64.b64decode(att.content_base64)
        except Exception:
            continue
        if not raw_bytes:
            continue

        ext = Path(att.filename).suffix.lower()
        safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", Path(att.filename).name) or "asset"
        digest_prefix = content_hash(raw_bytes)[:10]

        if ext in _IMAGE_EXTS:
            img_file = target_dir / f"{digest_prefix}_{safe_name}"
            img_file.write_bytes(raw_bytes)
            img_path_str = str(img_file.resolve())
            if img_path_str not in merged_images:
                merged_images.append(img_path_str)
            continue

        parsed_ast = default_bundle_parser.parse_one((safe_name, raw_bytes))
        for node in parsed_ast:
            if isinstance(node, TextNode) and node.text.strip():
                if "/hidden[" in node.path:
                    text_blocks.append(f"[HIDDEN_BLOCK] {node.text.strip()}")
                else:
                    text_blocks.append(node.text.strip())
            elif isinstance(node, ImageNode):
                if node.alt == "" and not Path(node.asset_path).is_file():
                    text_blocks.append(f"[HTML_IMG_MISSING_ALT] {node.asset_path}")
                elif node.asset_path and node.asset_path not in merged_images:
                    merged_images.append(node.asset_path)

    dedup_images: list[str] = []
    seen_img_hashes: set[str] = set()
    for img_p in merged_images:
        p_obj = Path(img_p)
        if p_obj.is_file():
            h_val = content_hash(p_obj.read_bytes())
            if h_val in seen_img_hashes:
                continue
            seen_img_hashes.add(h_val)
        dedup_images.append(img_p)
    return "\n\n".join(text_blocks), dedup_images


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("", response_model=SubmissionResponse, status_code=201)
async def create_submission(
    req: CreateSubmissionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> SubmissionResponse:
    canon = get_canon(req.canon_id)
    raw_content, all_image_paths = _ingest_bundle_attachments(
        req.raw_content, req.image_paths, req.attachments
    )
    if all_image_paths:
        extra_blocks = [
            f"{chr(33)}{chr(91)}Banner{chr(93)}{chr(40)}{img_p}{chr(41)}"
            for img_p in all_image_paths
            if img_p and img_p not in raw_content
        ]
        if extra_blocks:
            suffix = "\n\n".join(extra_blocks)
            raw_content = f"{raw_content.rstrip()}\n\n{suffix}" if raw_content.strip() else suffix

    c_hash = content_hash(raw_content.encode())

    sub = await repos.create_submission(
        session,
        title=req.title,
        raw_content=raw_content,
        content_hash=c_hash,
        canon_id=canon.id,
        canon_hash=canon.hash,
        creator_id=user.id,
    )

    return _to_response(sub)


@router.post("/upload", response_model=SubmissionResponse, status_code=201)
async def upload_submission_bundle(
    req: CreateSubmissionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> SubmissionResponse:
    """Dedicated multimodal bundle upload endpoint for `.docx`, `.pdf`, `.html`, `.png`, `.jpg`."""
    return await create_submission(req, session, user)


def _can_user_access_submission(user: CurrentUser, sub: Any) -> bool:
    """Enforce strict account and workflow-stage isolation across user accounts.

    - A user always sees campaigns they personally created (`sub.creator_id == user.id`).
    - Creator accounts (`role == 'creator'`) are strictly isolated to their own account
      and NEVER see another account's campaigns.
    - Unsubmitted Stage 1 drafts (`status in ('draft', 'changes_requested')`) are
      private to the Creator account that uploaded them and NEVER leak into another
      user's Brand Manager or Legal Reviewer queue until submitted (`status == 'in_review'`).
    - Brand Managers (`reviewer`) and Legal Reviewers (`admin`) only see other accounts'
      campaigns once those campaigns have been explicitly submitted into review
      (`status in ('in_review', 'approved', 'published')`).
    """
    sub_creator_id = getattr(sub, "creator_id", None)
    user_id = getattr(user, "id", None)
    if sub_creator_id is not None and user_id is not None and int(sub_creator_id) == int(user_id):
        return True

    role = str(getattr(user, "role", "creator")).lower()
    status = str(getattr(sub, "status", "draft")).lower()

    if role == "creator":
        return False

    if status in ("draft", "changes_requested"):
        return False

    if role in ("reviewer", "admin"):
        return status in ("in_review", "approved", "published")

    return False


@router.get("", response_model=list[SubmissionResponse])
async def list_submissions(
    session: SessionDep,
    user: CurrentUser,
) -> list[SubmissionResponse]:
    subs = await repos.list_submissions(session)
    visible = [s for s in subs if _can_user_access_submission(user, s)]
    return [_to_response(s) for s in visible]


@router.get("/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> SubmissionResponse:
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if str(getattr(user, "role", "")).lower() == "creator" and int(
        getattr(sub, "creator_id", -1)
    ) != int(getattr(user, "id", -2)):
        raise HTTPException(
            status_code=403,
            detail="Access denied: this campaign belongs to another Creator account",
        )
    return _to_response(sub)


@router.delete("/{submission_id}")
async def remove_submission(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> dict[str, Any]:
    """Delete a submission bundle from the workspace queue (owner or admin only)."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if (
        int(getattr(sub, "creator_id", -1)) != int(getattr(user, "id", -2))
        and str(getattr(user, "role", "")).lower() != "admin"
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only delete campaigns uploaded by your own account",
        )
    if hasattr(repos, "delete_submission"):
        deleted = await repos.delete_submission(session, submission_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Submission not found")
        return {"deleted": True, "id": submission_id}
    raise HTTPException(status_code=404, detail="Delete not supported")


@router.put("/{submission_id}/content", response_model=SubmissionResponse)
async def update_submission_raw_content(
    submission_id: int,
    req: UpdateSubmissionContentRequest,
    session: SessionDep,
    user: CurrentUser,
) -> SubmissionResponse:
    """Save edited campaign text as a new immutable revision and re-scan findings."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.status not in ("draft", "changes_requested"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot edit content while submission is in '{sub.status}' state. "
                "Recall to draft or request changes first."
            ),
        )

    # Preserve embedded ![Banner](...) image blocks if not present in the edited text
    existing_blocks = [b.strip() for b in _BLOCK_SPLIT_RE.split(sub.raw_content) if b.strip()]
    preserved_images = [
        b for b in existing_blocks if b.startswith("![") and "](" in b and b not in req.raw_content
    ]
    cleaned_text = req.raw_content.strip()
    if preserved_images:
        img_suffix = "\n\n".join(preserved_images)
        new_raw = f"{cleaned_text}\n\n{img_suffix}" if cleaned_text else img_suffix
    else:
        new_raw = cleaned_text

    new_c_hash = content_hash(new_raw.encode("utf-8"))
    updated_sub = await repos.update_submission_content(
        session,
        submission_id,
        raw_content=new_raw,
        content_hash=new_c_hash,
        actor_id=user.id,
        change_note=req.change_note.strip() or "Edited campaign copy in Review Studio",
    )
    if updated_sub is not None:
        sub = updated_sub

    canon = get_canon(sub.canon_id)
    ast = _parse_submission_ast(sub.raw_content)
    raw_findings = await run_checks_collect(ast, canon)
    calibrated = default_calibrator.filter_and_calibrate_findings(raw_findings, alpha=req.alpha)
    await repos.save_findings(session, submission_id, calibrated)
    if hasattr(session, "refresh"):
        await session.refresh(sub)

    return _to_response(sub)


@router.get("/{submission_id}/assets/{asset_index}")
async def get_submission_asset(
    submission_id: int,
    asset_index: int,
    session: SessionDep,
) -> Response:
    """Serve an attached campaign banner image by its 0-based `ImageNode` index."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    ast = _parse_submission_ast(sub.raw_content)
    img_nodes = [n for n in ast.of_kind(NodeKind.IMAGE) if isinstance(n, ImageNode)]
    if not (0 <= asset_index < len(img_nodes)):
        raise HTTPException(status_code=404, detail="Image asset not found")

    asset_path = Path(img_nodes[asset_index].asset_path)
    if not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Image asset file missing on disk")

    suffix = asset_path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = mime_map.get(suffix, "application/octet-stream")
    return Response(content=asset_path.read_bytes(), media_type=media_type)


async def _persist_scan_findings(submission_id: int, collected: list[Finding]) -> None:
    """Persist scan findings in an isolated async session after SSE streaming completes."""
    from canongate.store.db import async_session as session_factory

    async with session_factory() as persist_session, persist_session.begin():
        await repos.save_findings(persist_session, submission_id, collected)


@router.post("/{submission_id}/scan")
async def scan_submission(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
    alpha: float = 0.10,
):
    """Run all checks on a submission, apply Conformal Risk Control (alpha), and stream via SSE."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    canon = get_canon(sub.canon_id)
    ast = _parse_submission_ast(sub.raw_content)
    conformal_cutoff = default_calibrator.threshold(alpha)

    async def event_generator() -> AsyncIterator[dict]:
        raw_collected: list[Finding] = []
        async for finding in run_checks(ast, canon):
            calibrated_batch = default_calibrator.filter_and_calibrate_findings(
                [finding], alpha=alpha
            )
            for cal_f in calibrated_batch:
                raw_collected.append(cal_f)
                yield {"event": "finding", "data": cal_f.model_dump_json()}

        raw_collected.sort(
            key=lambda f: (
                ast.index_of(f.node_id),
                f.locator.sort_key,
                -f.severity,
                f.check_id,
                str(f.id),
            )
        )
        await _persist_scan_findings(submission_id, raw_collected)
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "total": len(raw_collected),
                    "alpha": round(alpha, 4),
                    "conformal_threshold": conformal_cutoff,
                }
            ),
        }

    return EventSourceResponse(event_generator())


@router.get("/{submission_id}/findings", response_model=list[FindingResponse])
async def get_findings(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> list[FindingResponse]:
    rows = await repos.get_findings_for_submission(session, submission_id)
    return [
        FindingResponse(
            row_id=r.id,
            finding_id=r.finding_id,
            check_id=r.check_id,
            node_id=r.node_id,
            severity=r.severity,
            message=r.message,
            resolution=r.resolution,
            resolution_reason=getattr(r, "resolution_reason", "") or "",
            payload=json.loads(r.payload_json),
        )
        for r in rows
    ]


@router.post(
    "/{submission_id}/findings/{finding_row_id}/rewrite",
    response_model=SurgicalRewriteResponse,
)
async def rewrite_finding_span(
    submission_id: int,
    finding_row_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> SurgicalRewriteResponse:
    """Invoke Tier 3 Constrained Rewriter (<=35% edit, PII scrub, Tier 1+2 re-verification)."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    row = await repos.get_finding_by_row_id(session, finding_row_id)
    if not row or row.submission_id != submission_id:
        raise HTTPException(status_code=404, detail="Finding not found")

    canon = get_canon(sub.canon_id)
    ast = _parse_submission_ast(sub.raw_content)
    text_nodes = [n for n in ast.of_kind(NodeKind.TEXT) if isinstance(n, TextNode)]
    target_node = next(
        (n for n in text_nodes if str(n.id) == str(row.node_id)),
        None,
    )
    if target_node is None:
        if not text_nodes:
            raise HTTPException(status_code=400, detail="Finding is not attached to a text node")
        domain_f_tmp = Finding.model_validate_json(row.payload_json)
        loc_tmp = domain_f_tmp.locator.model_dump()
        s_tmp = int(loc_tmp.get("start", -1))
        e_tmp = int(loc_tmp.get("end", -1))
        ev_tmp = domain_f_tmp.evidence.model_dump()
        probe_tmp = (
            str(
                ev_tmp.get("draft_value")
                or ev_tmp.get("matched_text")
                or ev_tmp.get("trigger_matched")
                or ""
            )
            .strip()
            .lower()
        )
        for cand in text_nodes:
            if 0 <= s_tmp < e_tmp <= len(cand.text):
                slice_txt = cand.text[s_tmp:e_tmp].lower()
                if not probe_tmp or probe_tmp in slice_txt or slice_txt in probe_tmp:
                    target_node = cand
                    break
        if target_node is None:
            target_node = (
                text_nodes[-1]
                if len(text_nodes) > 1 and text_nodes[0].text.startswith("#")
                else text_nodes[0]
            )

    domain_finding = Finding.model_validate_json(row.payload_json)
    result = await default_constrained_rewriter.rewrite(
        target_node,
        domain_finding,
        canon,
        verify_fn=run_checks_collect,
    )

    payload_dict = json.loads(row.payload_json)
    sug_dict = json.loads(result.suggestion.model_dump_json())
    sug_dict["explanation"] = result.provider_notice
    payload_dict["suggestion"] = sug_dict
    if isinstance(payload_dict.get("trace"), dict):
        is_ai = bool(result.context_trace.get("ai_used", False))
        is_ext = is_ai and not result.used_provider.startswith("ollama")
        payload_dict["trace"]["tier"] = "generative" if is_ai else "deterministic"
        payload_dict["trace"]["ai_used"] = is_ai
        payload_dict["trace"]["external_call"] = is_ext
        payload_dict["trace"]["model_sha"] = result.used_provider
        payload_dict["trace"]["model_name"] = result.used_provider
        payload_dict["trace"]["external_service"] = (
            result.used_provider if is_ext else "Local (No API Key)"
        )
        payload_dict["trace"]["rewriter_provider"] = result.used_provider
        payload_dict["trace"]["provider_notice"] = result.provider_notice
        payload_dict["trace"]["api_key_configured"] = result.api_key_configured
    await repos.update_finding_node_and_payload(
        session,
        row.id,
        node_id=str(row.node_id),
        payload_json=json.dumps(payload_dict),
    )

    return SurgicalRewriteResponse(
        row_id=row.id,
        finding_id=row.finding_id,
        original_text=result.original_text,
        rewritten_text=result.rewritten_text,
        edit_distance_ratio=result.edit_distance_ratio,
        max_edit_distance_ratio=result.max_edit_distance_ratio,
        reverified=result.reverified,
        remaining_findings_count=result.remaining_findings_count,
        pii_masked_count=result.pii_masked_count,
        masked_prompt_preview=result.masked_prompt_preview,
        used_provider=result.used_provider,
        api_key_configured=result.api_key_configured,
        provider_notice=result.provider_notice,
        quality_gates=result.quality_gates,
        context_trace=result.context_trace,
        suggestion=sug_dict,
    )


@router.get(
    "/{submission_id}/comments",
    response_model=list[SubmissionCommentResponse],
)
async def list_submission_comments(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
    finding_id: int | None = None,
) -> list[SubmissionCommentResponse]:
    """List inline comment threads for a submission (optionally filtered by finding_id)."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    rows = await repos.list_comments_for_submission(session, submission_id, finding_id=finding_id)
    return [
        SubmissionCommentResponse(
            id=r.id,
            submission_id=r.submission_id,
            finding_id=r.finding_id,
            author_id=r.author_id,
            author_name=r.author_name or f"user_{r.author_id}",
            role=r.role,
            body=r.body,
            created_at=str(r.created_at),
        )
        for r in rows
    ]


@router.post(
    "/{submission_id}/comments",
    response_model=SubmissionCommentResponse,
    status_code=201,
)
async def add_submission_comment(
    submission_id: int,
    req: CreateCommentRequest,
    session: SessionDep,
    user: CurrentUser,
) -> SubmissionCommentResponse:
    """Create an inline comment on a submission or a specific finding row."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    body = req.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Comment body cannot be empty")
    row = await repos.create_comment(
        session,
        submission_id=submission_id,
        finding_id=req.finding_id,
        author_id=user.id,
        author_name=getattr(user, "display_name", "") or getattr(user, "username", "user"),
        role=str(user.role),
        body=body,
    )
    return SubmissionCommentResponse(
        id=row.id,
        submission_id=row.submission_id,
        finding_id=row.finding_id,
        author_id=row.author_id,
        author_name=row.author_name,
        role=row.role,
        body=row.body,
        created_at=str(row.created_at),
    )


@router.patch("/{submission_id}/findings/{finding_row_id}", response_model=FindingResponse)
async def resolve_finding(
    submission_id: int,
    finding_row_id: int,
    req: FindingResolutionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> FindingResponse:
    row = await repos.get_finding_by_row_id(session, finding_row_id)
    if not row or row.submission_id != submission_id:
        raise HTTPException(status_code=404, detail="Finding not found")

    try:
        validate_resolution(
            req.resolution,
            severity=row.severity,
            role=Role(user.role),
            reason=req.reason,
        )
    except ResolutionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None

    if req.resolution == "accepted" and req.apply_suggestion:
        await _apply_accepted_suggestion(session, submission_id, row, actor_id=user.id)

    try:
        row = await repos.resolve_finding(
            session,
            finding_row_id,
            resolution=req.resolution,
            resolved_by=user.id,
            reason=(req.reason or "").strip(),
        )
    except TypeError:
        row = await repos.resolve_finding(
            session,
            finding_row_id,
            resolution=req.resolution,
            resolved_by=user.id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Finding not found")

    return FindingResponse(
        row_id=row.id,
        finding_id=row.finding_id,
        check_id=row.check_id,
        node_id=row.node_id,
        severity=row.severity,
        message=row.message,
        resolution=row.resolution,
        resolution_reason=getattr(row, "resolution_reason", "") or (req.reason or "").strip(),
        payload=json.loads(row.payload_json),
    )


@router.post("/{submission_id}/workflow", response_model=SubmissionResponse)
async def workflow_action(
    submission_id: int,
    req: WorkflowActionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> SubmissionResponse:
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    try:
        action = Action(req.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid action: {req.action}") from exc

    role = Role(user.role)
    current = Status(sub.status)

    try:
        new_status = next_status(current, action, role)
    except TransitionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None

    # Enforce Blocker Gate before approving or publishing a submission
    if action in (Action.APPROVE, Action.PUBLISH):
        finding_rows = await repos.get_findings_for_submission(session, submission_id)
        open_blockers = [f for f in finding_rows if f.severity >= 50 and f.resolution == "open"]
        if open_blockers:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot {action.value}: {len(open_blockers)} unresolved blocker "
                    "finding(s) remain open."
                ),
            )

    # Hash chain: get previous event hash
    events = await repos.get_events_for_submission(session, submission_id)
    prev_hash = events[-1].event_hash if events else GENESIS_HASH
    now = dt.datetime.now(dt.UTC).isoformat()
    event_hash = compute_event_hash(
        prev_hash=prev_hash,
        submission_id=submission_id,
        action=action.value,
        actor_id=user.id,
        timestamp=now,
    )

    await repos.append_event(
        session,
        submission_id=submission_id,
        action=action.value,
        from_status=current.value,
        to_status=new_status.value,
        actor_id=user.id,
        comment=req.comment,
        prev_hash=prev_hash,
        event_hash=event_hash,
        created_at=now,
    )

    if hasattr(repos, "update_submission_status"):
        sub = await repos.update_submission_status(session, sub, new_status.value)
    else:
        sub.status = new_status.value
        if hasattr(session, "flush"):
            await session.flush()
        refreshed_sub = await repos.get_submission(session, submission_id)
        if refreshed_sub is not None:
            sub = refreshed_sub

    # Outbound C2PA Asset Signing on approval/publishing using real ECDSA P-256 credentials
    if new_status in (Status.APPROVED, Status.PUBLISHED):
        parsed_ast = _parse_submission_ast(sub.raw_content)
        img_nodes = list(parsed_ast.of_kind(NodeKind.IMAGE))
        if img_nodes:
            all_events = await repos.get_events_for_submission(session, submission_id)
            leaves = [ev.event_hash.encode() for ev in all_events]
            m_root = MerkleTree(leaves).root_hex if leaves else "00" * 32

            for img in img_nodes:
                src_p = Path(img.asset_path)
                if src_p.is_file():
                    try:
                        manifest = build_governance_manifest(
                            submission_id=submission_id,
                            canon_id=sub.canon_id,
                            canon_hash=sub.canon_hash,
                            content_hash=sub.content_hash,
                            merkle_root=m_root,
                            approved_by=f"user_{user.id}",
                            approved_at=now,
                        )
                        out_p = src_p.with_name(f"{src_p.stem}_signed{src_p.suffix}")
                        sign_approved_asset(
                            source_path=src_p,
                            output_path=out_p,
                            mime_type=(
                                "image/png" if src_p.suffix.lower() == ".png" else "image/jpeg"
                            ),
                            manifest_def=manifest,
                        )
                    except Exception:
                        pass

    return _to_response(sub)


@router.get("/{submission_id}/audit")
async def get_audit_trail(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
):
    events = await repos.get_events_for_submission(session, submission_id)
    if not events:
        return []

    leaves = [e.event_hash.encode() for e in events]
    tree = MerkleTree(leaves)
    merkle_root = tree.root_hex

    server_key = derive_audit_signing_key(submission_id)
    now_iso = dt.datetime.now(dt.UTC).isoformat()
    sth = tree.sign_head(now_iso, server_key)
    sth_dict = sth.to_dict()

    enriched = []
    for idx, e in enumerate(events):
        audit_path = tree.prove_inclusion(idx)
        enriched.append(
            {
                "id": e.id,
                "submission_id": e.submission_id,
                "action": e.action,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "actor_id": e.actor_id,
                "comment": e.comment,
                "prev_hash": e.prev_hash,
                "event_hash": e.event_hash,
                "created_at": e.created_at,
                "leaf_index": idx,
                "audit_path": audit_path,
                "tree_size": len(tree),
                "merkle_root": merkle_root,
                "tree_head": sth_dict,
            }
        )
    return enriched


@router.get("/{submission_id}/audit/tree-head")
async def get_audit_tree_head(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
):
    """Retrieve the RFC 9162 Signed Tree Head (STH) with Ed25519 signature."""
    events = await repos.get_events_for_submission(session, submission_id)
    if not events:
        raise HTTPException(status_code=404, detail="No audit events for this submission")

    leaves = [e.event_hash.encode() for e in events]
    tree = MerkleTree(leaves)
    server_key = derive_audit_signing_key(submission_id)
    now_iso = dt.datetime.now(dt.UTC).isoformat()
    sth = tree.sign_head(now_iso, server_key)
    return sth.to_dict()


@router.get("/{submission_id}/certificate")
async def get_governance_certificate(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> dict[str, Any]:
    """Export a self-contained signed governance certificate verifiable via `canongate verify`."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    events = await repos.get_events_for_submission(session, submission_id)
    cert = GovernanceCertificate.build(
        submission_id=sub.id,
        title=sub.title,
        status=sub.status,
        content_hash=sub.content_hash,
        canon_id=sub.canon_id,
        canon_hash=sub.canon_hash,
        event_rows=events,
    )
    out = cert.to_dict()
    img_nodes = list(_parse_submission_ast(sub.raw_content).of_kind(NodeKind.IMAGE))
    c2pa_manifests: list[dict[str, Any]] = []
    for img in img_nodes:
        src_p = Path(img.asset_path)
        sidecar_p = src_p.with_name(f"{src_p.stem}_signed{src_p.suffix}.c2pa.json")
        if sidecar_p.is_file():
            with contextlib.suppress(Exception):
                c2pa_manifests.append(json.loads(sidecar_p.read_text(encoding="utf-8")))
    if c2pa_manifests:
        out["c2pa_manifests"] = c2pa_manifests
    return out


@router.get("/{submission_id}/c2pa")
async def get_submission_c2pa_manifests(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> dict[str, Any]:
    """Return signed outbound C2PA v2.3 manifests and X.509 certificates for visual assets."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    img_nodes = list(_parse_submission_ast(sub.raw_content).of_kind(NodeKind.IMAGE))
    manifests: list[dict[str, Any]] = []
    for img in img_nodes:
        src_p = Path(img.asset_path)
        signed_p = src_p.with_name(f"{src_p.stem}_signed{src_p.suffix}")
        sidecar_p = src_p.with_name(f"{src_p.stem}_signed{src_p.suffix}.c2pa.json")
        if sidecar_p.is_file():
            with contextlib.suppress(Exception):
                sc = json.loads(sidecar_p.read_text(encoding="utf-8"))
                sc["node_id"] = str(img.id)
                sc["signed_asset_exists"] = signed_p.is_file()
                manifests.append(sc)
    return {
        "submission_id": sub.id,
        "status": sub.status,
        "c2pa_count": len(manifests),
        "manifests": manifests,
    }


@router.get("/{submission_id}/versions", response_model=list[SubmissionVersionResponse])
async def get_submission_versions(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> list[SubmissionVersionResponse]:
    """Return immutable revision history for `submission_id`."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    if hasattr(repos, "list_submission_versions"):
        rows = await repos.list_submission_versions(session, submission_id)
        if rows:
            return [
                SubmissionVersionResponse(
                    version_number=r.version_number,
                    content_hash=r.content_hash,
                    canon_hash=r.canon_hash,
                    raw_content=r.raw_content,
                    created_by=r.created_by,
                    change_note=getattr(r, "change_note", "") or "",
                    created_at=str(r.created_at),
                )
                for r in rows
            ]

    return [
        SubmissionVersionResponse(
            version_number=1,
            content_hash=sub.content_hash,
            canon_hash=sub.canon_hash,
            raw_content=sub.raw_content,
            created_by=sub.creator_id,
            change_note="Initial submission",
            created_at=str(sub.created_at),
        )
    ]


@router.get("/{submission_id}/replay-manifest")
async def get_replay_manifest(
    submission_id: int,
    session: SessionDep,
    user: CurrentUser,
    alpha: float = 0.10,
) -> dict[str, Any]:
    """Export the deterministic replay manifest pinning AST hashes, Canon hash,
    check versions, and alpha.
    """
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    ast = _parse_submission_ast(sub.raw_content)
    ast_nodes = [{"path": n.path, "node_id": str(n.id), "kind": str(n.kind)} for n in ast.nodes]
    ast_hash = content_hash(
        json.dumps(ast_nodes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    checks_meta = sorted(
        (
            {"check_id": c.check_id, "check_version": c.check_version}
            for c in Check.get_all().values()
        ),
        key=lambda item: item["check_id"],
    )
    conformal_threshold = default_calibrator.threshold(alpha)
    core_manifest = {
        "submission_id": sub.id,
        "content_hash": sub.content_hash,
        "ast_hash": ast_hash,
        "ast_nodes": ast_nodes,
        "canon_id": sub.canon_id,
        "canon_hash": sub.canon_hash,
        "alpha": round(alpha, 4),
        "conformal_threshold": conformal_threshold,
        "registered_checks": checks_meta,
    }
    manifest_hash = content_hash(
        json.dumps(core_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return {**core_manifest, "manifest_hash": manifest_hash}


# ── Helpers ──────────────────────────────────────────────────────────

_PARA_IDX_RE = re.compile(r"p\[(\d+)\]")
_BLOCK_SPLIT_RE = re.compile(r"\n{2,}")


async def _apply_accepted_suggestion(
    session: Any,
    submission_id: int,
    row: Any,
    *,
    actor_id: int | None = None,
) -> None:
    """Apply `suggestion.replacements` to `sub.raw_content` and shift co-located spans."""
    try:
        payload = json.loads(row.payload_json)
    except Exception:
        return

    suggestion = payload.get("suggestion")
    if not isinstance(suggestion, dict):
        return
    raw_replacements = suggestion.get("replacements") or []
    if not raw_replacements:
        return

    sub = await repos.get_submission(session, submission_id)
    if not sub or not getattr(sub, "raw_content", ""):
        return

    old_node_id = str(row.node_id)
    ast = _parse_submission_ast(sub.raw_content)
    target_node = next(
        (
            n
            for n in ast.of_kind(NodeKind.TEXT)
            if isinstance(n, TextNode) and str(n.id) == old_node_id
        ),
        None,
    )
    if target_node is None:
        return

    old_text = target_node.text
    valid_edits: list[tuple[int, int, str]] = []
    for rep in raw_replacements:
        span = rep.get("span") if isinstance(rep, dict) else None
        rep_str = rep.get("replacement") if isinstance(rep, dict) else None
        if not isinstance(span, dict) or not isinstance(rep_str, str):
            continue
        s = span.get("start")
        e = span.get("end")
        if isinstance(s, int) and isinstance(e, int) and 0 <= s <= e <= len(old_text):
            valid_edits.append((s, e, rep_str))

    if not valid_edits:
        return

    valid_edits.sort(key=lambda item: item[0], reverse=True)
    new_node_text = old_text
    for s, e, rep_str in valid_edits:
        new_node_text = new_node_text[:s] + rep_str + new_node_text[e:]

    new_raw_content = _replace_node_in_raw_content(
        sub.raw_content,
        target_node=target_node,
        new_node_text=new_node_text,
        edits=valid_edits,
    )
    if new_raw_content == sub.raw_content:
        return

    new_c_hash = content_hash(new_raw_content.encode("utf-8"))
    if hasattr(repos, "update_submission_content"):
        try:
            await repos.update_submission_content(
                session,
                submission_id,
                raw_content=new_raw_content,
                content_hash=new_c_hash,
                actor_id=actor_id,
                change_note=f"Accepted suggestion on finding #{row.id}",
            )
        except TypeError:
            await repos.update_submission_content(
                session,
                submission_id,
                raw_content=new_raw_content,
                content_hash=new_c_hash,
            )
    else:
        sub.raw_content = new_raw_content
        sub.content_hash = new_c_hash

    new_ast = _parse_submission_ast(new_raw_content)
    updated_node = next(
        (
            n
            for n in new_ast.of_kind(NodeKind.TEXT)
            if isinstance(n, TextNode) and n.path == target_node.path
        ),
        None,
    )
    new_node_id = str(updated_node.id) if updated_node is not None else old_node_id

    all_rows = await repos.get_findings_for_submission(session, submission_id)
    for other in all_rows:
        if str(other.node_id) != old_node_id:
            continue
        try:
            other_payload = json.loads(other.payload_json)
        except Exception:
            continue

        if other.id != row.id and other.resolution == "open":
            _shift_or_supersede_finding_payload(other_payload, valid_edits)

        other_payload["node_id"] = new_node_id
        new_payload_json = json.dumps(other_payload)
        if hasattr(repos, "update_finding_node_and_payload"):
            await repos.update_finding_node_and_payload(
                session,
                other.id,
                node_id=new_node_id,
                payload_json=new_payload_json,
            )
        else:
            other.node_id = new_node_id
            other.payload_json = new_payload_json


def _replace_node_in_raw_content(
    raw_content: str,
    *,
    target_node: TextNode,
    new_node_text: str,
    edits: list[tuple[int, int, str]],
) -> str:
    """Replace the target node's text inside `raw_content`, preserving paragraph/table structure."""
    blocks = [b.strip() for b in _BLOCK_SPLIT_RE.split(raw_content) if b.strip()]
    m = _PARA_IDX_RE.search(target_node.path)
    para_idx = int(m.group(1)) if m else -1

    if "/table[" not in target_node.path:
        if 0 <= para_idx < len(blocks):
            blocks[para_idx] = new_node_text
            return "\n\n".join(blocks)
        return raw_content.replace(target_node.text, new_node_text, 1)

    # Linearized Markdown table row (`text/p[idx]/table[t]/r[row_idx]`)
    if 0 <= para_idx < len(blocks):
        table_block = blocks[para_idx]
        updated_block = table_block
        for s, e, rep_str in edits:
            old_sub = target_node.text[s:e]
            if old_sub and old_sub in updated_block:
                updated_block = updated_block.replace(old_sub, rep_str, 1)
            elif s == 0 and e == len(target_node.text) and ":" in target_node.text:
                cell_val = target_node.text.split(":", maxsplit=2)[-1].strip()
                if cell_val and cell_val in updated_block:
                    updated_block = updated_block.replace(cell_val, rep_str, 1)
        blocks[para_idx] = updated_block
        return "\n\n".join(blocks)

    return raw_content


def _shift_or_supersede_finding_payload(
    payload: dict[str, Any],
    applied_edits: list[tuple[int, int, str]],
) -> None:
    """Shift character offsets of co-located open findings or clear overlapped replacements."""
    loc = payload.get("locator")
    if not isinstance(loc, dict):
        return
    os = loc.get("start")
    oe = loc.get("end")
    if not isinstance(os, int) or not isinstance(oe, int):
        return

    overlapped = False
    net_shift = 0
    for s, e, rep_str in applied_edits:
        delta = len(rep_str) - (e - s)
        if os >= e:
            net_shift += delta
        elif oe <= s:
            continue
        else:
            overlapped = True
            break

    if overlapped:
        sug = payload.get("suggestion")
        if isinstance(sug, dict):
            sug["replacements"] = []
        return

    if net_shift != 0:
        loc["start"] = os + net_shift
        loc["end"] = oe + net_shift
        sug = payload.get("suggestion")
        if isinstance(sug, dict):
            for rep in sug.get("replacements") or []:
                r_span = rep.get("span") if isinstance(rep, dict) else None
                if isinstance(r_span, dict):
                    rs = r_span.get("start")
                    re_ = r_span.get("end")
                    if isinstance(rs, int) and isinstance(re_, int):
                        r_span["start"] = rs + net_shift
                        r_span["end"] = re_ + net_shift


_TEXT_AST_CACHE: dict[str, ContentAST] = {}


def _parse_submission_ast(raw: str) -> ContentAST:
    """Parse raw submission text into a `ContentAST`, linearizing Markdown pipe tables."""
    can_cache_text = "![" not in raw
    if can_cache_text:
        cached = _TEXT_AST_CACHE.get(raw)
        if cached is not None:
            return cached
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
    res_ast = ContentAST(nodes=tuple(expanded_nodes))
    if can_cache_text:
        if len(_TEXT_AST_CACHE) >= 512:
            _TEXT_AST_CACHE.clear()
        _TEXT_AST_CACHE[raw] = res_ast
    return res_ast


def _to_response(sub) -> SubmissionResponse:
    raw = getattr(sub, "raw_content", "") or ""
    ast = _parse_submission_ast(raw)
    text_nodes = [n for n in ast.of_kind(NodeKind.TEXT) if isinstance(n, TextNode)]
    p_ids = [n.id for n in text_nodes]
    t_blocks = [n.text for n in text_nodes]
    img_nodes_raw = [n for n in ast.of_kind(NodeKind.IMAGE) if isinstance(n, ImageNode)]
    img_paths = [n.asset_path for n in img_nodes_raw]
    img_meta = [
        ImageNodeMetaDto(
            index=idx,
            node_id=str(n.id),
            asset_path=n.asset_path,
            width=n.width,
            height=n.height,
            alt=n.alt,
            url=f"/api/submissions/{sub.id}/assets/{idx}",
        )
        for idx, n in enumerate(img_nodes_raw)
    ]

    return SubmissionResponse(
        id=sub.id,
        title=sub.title,
        status=sub.status,
        content_hash=sub.content_hash,
        canon_id=sub.canon_id,
        canon_hash=sub.canon_hash,
        creator_id=sub.creator_id,
        created_at=str(sub.created_at),
        updated_at=str(sub.updated_at),
        raw_content=raw,
        paragraph_node_ids=p_ids,
        text_blocks=t_blocks,
        image_paths=img_paths,
        image_nodes=img_meta,
    )
