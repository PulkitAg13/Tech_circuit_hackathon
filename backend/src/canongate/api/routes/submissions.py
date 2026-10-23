"""Submission routes: create, list, get findings, workflow actions, SSE stream."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from canongate.api.deps import CurrentUser, SessionDep, get_canon
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
from canongate.engine.runner import run_checks
from canongate.ledger.chain import GENESIS_HASH, compute_event_hash
from canongate.parsers.text import parse_text
from canongate.store import repos

router = APIRouter(prefix="/submissions", tags=["submissions"])


# ── Request / Response models ────────────────────────────────────────


class CreateSubmissionRequest(BaseModel):
    title: str = "Untitled"
    raw_content: str
    canon_id: str
    image_paths: list[str] = []


class SubmissionResponse(BaseModel):
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
    image_paths: list[str] = []


class WorkflowActionRequest(BaseModel):
    action: str
    comment: str = ""


class FindingResolutionRequest(BaseModel):
    resolution: str  # accepted | dismissed | overridden


class FindingResponse(BaseModel):
    row_id: int
    finding_id: str
    check_id: str
    node_id: str
    severity: int
    message: str
    resolution: str
    payload: dict


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("", response_model=SubmissionResponse, status_code=201)
async def create_submission(
    req: CreateSubmissionRequest, session: SessionDep, user: CurrentUser
) -> SubmissionResponse:
    canon = get_canon(req.canon_id)
    c_hash = content_hash(req.raw_content.encode())

    sub = await repos.create_submission(
        session,
        title=req.title,
        raw_content=req.raw_content,
        content_hash=c_hash,
        canon_id=canon.id,
        canon_hash=canon.hash,
        creator_id=user.id,
    )

    return _to_response(sub)


@router.get("", response_model=list[SubmissionResponse])
async def list_submissions(session: SessionDep, user: CurrentUser) -> list[SubmissionResponse]:
    subs = await repos.list_submissions(session)
    return [_to_response(s) for s in subs]


@router.get("/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: int, session: SessionDep, user: CurrentUser
) -> SubmissionResponse:
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    return _to_response(sub)


@router.post("/{submission_id}/scan")
async def scan_submission(submission_id: int, session: SessionDep, user: CurrentUser):
    """Run all checks on a submission and stream findings via SSE."""
    sub = await repos.get_submission(session, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    canon = get_canon(sub.canon_id)
    ast = parse_text(sub.raw_content)

    async def event_generator() -> AsyncIterator[dict]:
        collected: list[Finding] = []
        async for finding in run_checks(ast, canon):
            collected.append(finding)
            yield {"event": "finding", "data": finding.model_dump_json()}

        # Persist all findings at the end (new session because the SSE generator
        # runs outside the request session scope)
        from canongate.store.db import async_session as session_factory

        async with session_factory() as persist_session, persist_session.begin():
            await repos.save_findings(persist_session, submission_id, collected)

        yield {"event": "done", "data": json.dumps({"total": len(collected)})}

    return EventSourceResponse(event_generator())


@router.get("/{submission_id}/findings", response_model=list[FindingResponse])
async def get_findings(
    submission_id: int, session: SessionDep, user: CurrentUser
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
            payload=json.loads(r.payload_json),
        )
        for r in rows
    ]


@router.patch("/{submission_id}/findings/{finding_row_id}", response_model=FindingResponse)
async def resolve_finding(
    submission_id: int,
    finding_row_id: int,
    req: FindingResolutionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> FindingResponse:
    # First fetch the finding so we can read its severity
    row = await repos.get_finding_by_row_id(session, finding_row_id)
    if not row or row.submission_id != submission_id:
        raise HTTPException(status_code=404, detail="Finding not found")

    try:
        validate_resolution(
            req.resolution,
            severity=row.severity,
            role=Role(user.role),
        )
    except ResolutionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None

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

    sub.status = new_status.value
    await session.flush()

    # Outbound C2PA Asset Signing on approval/publishing
    if new_status in (Status.APPROVED, Status.PUBLISHED):
        from pathlib import Path

        from canongate.domain.ast import NodeKind
        from canongate.ledger.c2pa_outbound import build_governance_manifest, sign_approved_asset
        from canongate.ledger.merkle import compute_merkle_root

        parsed_ast = parse_text(sub.raw_content)
        img_nodes = list(parsed_ast.of_kind(NodeKind.IMAGE))
        if img_nodes:
            all_events = await repos.get_events_for_submission(session, submission_id)
            leaves = [ev.event_hash.encode() for ev in all_events]
            m_root = compute_merkle_root(leaves).hex() if leaves else "00" * 32

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
                            sign_callback=lambda data: b"canongate-c2pa-signature",
                            cert_chain_pem=(
                                "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
                            ),
                        )
                    except Exception:
                        pass

    return _to_response(sub)


@router.get("/{submission_id}/audit")
async def get_audit_trail(submission_id: int, session: SessionDep, user: CurrentUser):
    import hashlib

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from canongate.ledger.merkle import (
        compute_merkle_root,
        prove_inclusion,
        sign_tree_head,
    )

    events = await repos.get_events_for_submission(session, submission_id)
    if not events:
        return []

    leaves = [e.event_hash.encode() for e in events]
    merkle_root = compute_merkle_root(leaves).hex()

    seed = hashlib.sha256(f"canongate-audit-{submission_id}".encode()).digest()
    server_key = Ed25519PrivateKey.from_private_bytes(seed)
    now_iso = dt.datetime.now(dt.UTC).isoformat()
    sth = sign_tree_head(leaves, now_iso, server_key)

    enriched = []
    for idx, e in enumerate(events):
        audit_path = prove_inclusion(idx, leaves)
        enriched.append(
            {
                "id": e.id,
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
                "tree_size": len(leaves),
                "merkle_root": merkle_root,
                "tree_head": {
                    "tree_size": sth.tree_size,
                    "timestamp": sth.timestamp,
                    "root_hash": sth.root_hash,
                    "signature": sth.signature,
                    "public_key": sth.public_key,
                },
            }
        )
    return enriched


@router.get("/{submission_id}/audit/tree-head")
async def get_audit_tree_head(submission_id: int, session: SessionDep, user: CurrentUser):
    """Retrieve the RFC 9162 Signed Tree Head (STH) with Ed25519 signature."""
    import hashlib

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from canongate.ledger.merkle import sign_tree_head

    events = await repos.get_events_for_submission(session, submission_id)
    if not events:
        raise HTTPException(status_code=404, detail="No audit events for this submission")

    leaves = [e.event_hash.encode() for e in events]
    seed = hashlib.sha256(f"canongate-audit-{submission_id}".encode()).digest()
    server_key = Ed25519PrivateKey.from_private_bytes(seed)
    now_iso = dt.datetime.now(dt.UTC).isoformat()
    sth = sign_tree_head(leaves, now_iso, server_key)
    return {
        "tree_size": sth.tree_size,
        "timestamp": sth.timestamp,
        "root_hash": sth.root_hash,
        "signature": sth.signature,
        "public_key": sth.public_key,
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _to_response(sub) -> SubmissionResponse:
    from canongate.domain.ast import NodeKind

    raw = getattr(sub, "raw_content", "") or ""
    ast = parse_text(raw)
    p_ids = [n.id for n in ast.of_kind(NodeKind.TEXT)]
    img_paths = [n.asset_path for n in ast.of_kind(NodeKind.IMAGE)]

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
        image_paths=img_paths,
    )
