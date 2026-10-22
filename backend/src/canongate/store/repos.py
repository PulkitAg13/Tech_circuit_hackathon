"""Repository layer: thin async wrappers around SQLAlchemy queries.

Each function takes an AsyncSession — dependency-injected from the API layer.
No business logic here, just persistence.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from canongate.domain.finding import Finding
from canongate.store.tables import FindingRow, SubmissionRow, UserRow, WorkflowEventRow

# ── Users ────────────────────────────────────────────────────────────


async def get_user_by_username(session: AsyncSession, username: str) -> UserRow | None:
    result = await session.execute(select(UserRow).where(UserRow.username == username))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession, *, username: str, display_name: str, role: str, password_hash: str
) -> UserRow:
    user = UserRow(
        username=username, display_name=display_name, role=role, password_hash=password_hash
    )
    session.add(user)
    await session.flush()
    return user


# ── Submissions ──────────────────────────────────────────────────────


async def create_submission(
    session: AsyncSession,
    *,
    title: str,
    raw_content: str,
    content_hash: str,
    canon_id: str,
    canon_hash: str,
    creator_id: int,
) -> SubmissionRow:
    sub = SubmissionRow(
        title=title,
        raw_content=raw_content,
        content_hash=content_hash,
        canon_id=canon_id,
        canon_hash=canon_hash,
        creator_id=creator_id,
    )
    session.add(sub)
    await session.flush()
    return sub


async def get_submission(session: AsyncSession, submission_id: int) -> SubmissionRow | None:
    result = await session.execute(select(SubmissionRow).where(SubmissionRow.id == submission_id))
    return result.scalar_one_or_none()


async def list_submissions(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[SubmissionRow]:
    result = await session.execute(
        select(SubmissionRow).order_by(SubmissionRow.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


# ── Findings ─────────────────────────────────────────────────────────


async def save_findings(
    session: AsyncSession,
    submission_id: int,
    findings: list[Finding],
) -> None:
    """Persist a batch of domain Findings as rows.

    Existing *open* findings for this submission are replaced.
    Already-resolved findings (accepted/dismissed/overridden) are kept
    so reviewer decisions survive a re-scan.
    """
    # Collect already-resolved finding_ids so we don't overwrite them
    existing = await session.execute(
        select(FindingRow).where(
            FindingRow.submission_id == submission_id,
            FindingRow.resolution != "open",
        )
    )
    resolved_ids = {r.finding_id for r in existing.scalars().all()}

    # Delete old open findings (they'll be replaced by this batch)
    await session.execute(
        delete(FindingRow).where(
            FindingRow.submission_id == submission_id,
            FindingRow.resolution == "open",
        )
    )

    for f in findings:
        if f.id in resolved_ids:
            continue  # don't overwrite a reviewer's decision
        row = FindingRow(
            finding_id=f.id,
            submission_id=submission_id,
            check_id=f.check_id,
            node_id=f.node_id,
            severity=f.severity,
            message=f.message,
            payload_json=f.model_dump_json(),
        )
        session.add(row)
    await session.flush()


async def get_findings_for_submission(
    session: AsyncSession, submission_id: int
) -> list[FindingRow]:
    result = await session.execute(
        select(FindingRow).where(FindingRow.submission_id == submission_id)
    )
    return list(result.scalars().all())


async def get_finding_by_row_id(
    session: AsyncSession,
    row_id: int,
) -> FindingRow | None:
    result = await session.execute(select(FindingRow).where(FindingRow.id == row_id))
    return result.scalar_one_or_none()


async def resolve_finding(
    session: AsyncSession, finding_row_id: int, *, resolution: str, resolved_by: int
) -> FindingRow | None:
    result = await session.execute(select(FindingRow).where(FindingRow.id == finding_row_id))
    row = result.scalar_one_or_none()
    if row:
        row.resolution = resolution
        row.resolved_by = resolved_by
        await session.flush()
    return row


# ── Workflow Events ──────────────────────────────────────────────────


async def append_event(
    session: AsyncSession,
    *,
    submission_id: int,
    action: str,
    from_status: str,
    to_status: str,
    actor_id: int,
    comment: str,
    prev_hash: str,
    event_hash: str,
    created_at: str,
) -> WorkflowEventRow:
    evt = WorkflowEventRow(
        submission_id=submission_id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        comment=comment,
        prev_hash=prev_hash,
        event_hash=event_hash,
        created_at=created_at,
    )
    session.add(evt)
    await session.flush()
    return evt


async def get_events_for_submission(
    session: AsyncSession, submission_id: int
) -> list[WorkflowEventRow]:
    result = await session.execute(
        select(WorkflowEventRow)
        .where(WorkflowEventRow.submission_id == submission_id)
        .order_by(WorkflowEventRow.id)
    )
    return list(result.scalars().all())


async def get_findings_for_canon(
    session: AsyncSession, canon_id: str
) -> list[FindingRow]:
    """Retrieve all finding rows across all submissions governed by canon_id."""
    result = await session.execute(
        select(FindingRow)
        .join(SubmissionRow, FindingRow.submission_id == SubmissionRow.id)
        .where(SubmissionRow.canon_id == canon_id)
    )
    return list(result.scalars().all())
