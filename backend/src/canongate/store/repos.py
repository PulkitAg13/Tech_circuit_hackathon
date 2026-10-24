"""Repository layer: thin async wrappers around SQLAlchemy or stdlib sqlite3 queries.

Each function takes an AsyncSession — dependency-injected from the API layer.
No business logic here, just persistence.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

from canongate.domain.finding import Finding
from canongate.store.tables import (
    HAS_SQLALCHEMY,
    FindingRow,
    SubmissionCommentRow,
    SubmissionRow,
    SubmissionVersionRow,
    UserRow,
    WorkflowEventRow,
)

if HAS_SQLALCHEMY:
    from sqlalchemy import delete, func, select
    from sqlalchemy.ext.asyncio import AsyncSession
else:
    from canongate.store.db import SqliteAsyncSession as AsyncSession  # type: ignore[assignment]


def _is_sqlite_session(session: Any) -> bool:
    return bool(getattr(session, "is_sqlite_fallback", False)) or hasattr(session, "conn")


def _parse_dt(val: Any) -> dt.datetime:
    if isinstance(val, dt.datetime):
        return val
    if isinstance(val, str) and val:
        try:
            return dt.datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            pass
    return dt.datetime.now(dt.UTC)


def _row_to_user(r: sqlite3.Row) -> UserRow:
    return UserRow(
        id=int(r["id"]),
        username=str(r["username"]),
        display_name=str(r["display_name"]),
        role=str(r["role"]),
        password_hash=str(r["password_hash"]),
        created_at=_parse_dt(r["created_at"]),
    )


def _row_to_submission(r: sqlite3.Row) -> SubmissionRow:
    keys = r.keys()
    return SubmissionRow(
        id=int(r["id"]),
        title=str(r["title"]),
        raw_content=str(r["raw_content"]),
        content_hash=str(r["content_hash"]),
        canon_id=str(r["canon_id"]),
        canon_hash=str(r["canon_hash"]),
        status=str(r["status"]),
        creator_id=int(r["creator_id"]),
        created_at=_parse_dt(r["created_at"] if "created_at" in keys else None),
        updated_at=_parse_dt(r["updated_at"] if "updated_at" in keys else None),
    )


def _row_to_version(r: sqlite3.Row) -> SubmissionVersionRow:
    keys = r.keys()
    return SubmissionVersionRow(
        id=int(r["id"]),
        submission_id=int(r["submission_id"]),
        version_number=int(r["version_number"]),
        raw_content=str(r["raw_content"]),
        content_hash=str(r["content_hash"]),
        canon_hash=str(r["canon_hash"]),
        created_by=int(r["created_by"]),
        change_note=str(r["change_note"]),
        created_at=_parse_dt(r["created_at"] if "created_at" in keys else None),
    )


def _row_to_finding(r: sqlite3.Row) -> FindingRow:
    keys = r.keys()
    return FindingRow(
        id=int(r["id"]),
        finding_id=str(r["finding_id"]),
        submission_id=int(r["submission_id"]),
        check_id=str(r["check_id"]),
        node_id=str(r["node_id"]),
        severity=int(r["severity"]),
        message=str(r["message"]),
        payload_json=str(r["payload_json"]),
        resolution=str(r["resolution"]),
        resolution_reason=str(r["resolution_reason"]) if "resolution_reason" in keys else "",
        resolved_by=int(r["resolved_by"]) if r["resolved_by"] is not None else None,
    )


def _row_to_comment(r: sqlite3.Row) -> SubmissionCommentRow:
    keys = r.keys()
    return SubmissionCommentRow(
        id=int(r["id"]),
        submission_id=int(r["submission_id"]),
        finding_id=int(r["finding_id"]) if r["finding_id"] is not None else None,
        author_id=int(r["author_id"]),
        author_name=str(r["author_name"]),
        role=str(r["role"]),
        body=str(r["body"]),
        created_at=_parse_dt(r["created_at"] if "created_at" in keys else None),
    )


def _row_to_event(r: sqlite3.Row) -> WorkflowEventRow:
    return WorkflowEventRow(
        id=int(r["id"]),
        submission_id=int(r["submission_id"]),
        action=str(r["action"]),
        from_status=str(r["from_status"]),
        to_status=str(r["to_status"]),
        actor_id=int(r["actor_id"]),
        comment=str(r["comment"]),
        prev_hash=str(r["prev_hash"]),
        event_hash=str(r["event_hash"]),
        created_at=str(r["created_at"]),
    )


# ── Users ────────────────────────────────────────────────────────────


async def get_user_by_username(session: AsyncSession, username: str) -> UserRow | None:
    if _is_sqlite_session(session):
        cur = session.conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        return _row_to_user(row) if row else None
    result = await session.execute(select(UserRow).where(UserRow.username == username))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession, *, username: str, display_name: str, role: str, password_hash: str
) -> UserRow:
    if _is_sqlite_session(session):
        now_iso = dt.datetime.now(dt.UTC).isoformat()
        cur = session.conn.execute(
            """
            INSERT INTO users (username, display_name, role, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, display_name, role, password_hash, now_iso),
        )
        session.conn.commit()
        user_id = int(cur.lastrowid or 1)
        return UserRow(
            id=user_id,
            username=username,
            display_name=display_name,
            role=role,
            password_hash=password_hash,
            created_at=_parse_dt(now_iso),
        )
    user = UserRow(
        username=username, display_name=display_name, role=role, password_hash=password_hash
    )
    session.add(user)
    await session.flush()
    return user


async def update_user_role(session: AsyncSession, user: UserRow, role: str) -> UserRow:
    """Update a user's RBAC role in both SQLite and SQLAlchemy modes."""
    user.role = role
    if _is_sqlite_session(session):
        session.conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user.id))
        session.conn.commit()
    else:
        await session.flush()
    return user


# ── Submissions & Immutable Revisions ────────────────────────────────


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
    if _is_sqlite_session(session):
        now_iso = dt.datetime.now(dt.UTC).isoformat()
        cur = session.conn.execute(
            """
            INSERT INTO submissions
            (title, status, raw_content, content_hash, canon_id, canon_hash,
             creator_id, created_at, updated_at)
            VALUES (?, 'draft', ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, raw_content, content_hash, canon_id, canon_hash, creator_id, now_iso, now_iso),
        )
        sub_id = int(cur.lastrowid or 1)
        session.conn.execute(
            """
            INSERT INTO submission_versions
            (submission_id, version_number, raw_content, content_hash,
             canon_hash, created_by, change_note, created_at)
            VALUES (?, 1, ?, ?, ?, ?, 'Initial submission', ?)
            """,
            (sub_id, raw_content, content_hash, canon_hash, creator_id, now_iso),
        )
        session.conn.commit()
        return SubmissionRow(
            id=sub_id,
            title=title,
            raw_content=raw_content,
            content_hash=content_hash,
            canon_id=canon_id,
            canon_hash=canon_hash,
            status="draft",
            creator_id=creator_id,
            created_at=_parse_dt(now_iso),
            updated_at=_parse_dt(now_iso),
        )
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

    ver = SubmissionVersionRow(
        submission_id=sub.id,
        version_number=1,
        raw_content=raw_content,
        content_hash=content_hash,
        canon_hash=canon_hash,
        created_by=creator_id,
        change_note="Initial submission",
    )
    session.add(ver)
    await session.flush()
    return sub


async def get_submission(session: AsyncSession, submission_id: int) -> SubmissionRow | None:
    if _is_sqlite_session(session):
        cur = session.conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,))
        row = cur.fetchone()
        return _row_to_submission(row) if row else None
    result = await session.execute(select(SubmissionRow).where(SubmissionRow.id == submission_id))
    return result.scalar_one_or_none()


async def delete_submission(session: AsyncSession, submission_id: int) -> bool:
    """Delete a submission and its associated findings, versions, comments, and events."""
    if _is_sqlite_session(session):
        cur = session.conn.execute("SELECT id FROM submissions WHERE id = ?", (submission_id,))
        if not cur.fetchone():
            return False
        for tbl in ("submission_comments", "findings", "submission_versions", "workflow_events"):
            session.conn.execute(f"DELETE FROM {tbl} WHERE submission_id = ?", (submission_id,))
        session.conn.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
        session.conn.commit()
        return True

    sub = await get_submission(session, submission_id)
    if not sub:
        return False
    await session.delete(sub)
    await session.flush()
    return True


async def list_submissions(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[SubmissionRow]:
    if _is_sqlite_session(session):
        cur = session.conn.execute(
            "SELECT * FROM submissions ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [_row_to_submission(r) for r in cur.fetchall()]
    result = await session.execute(
        select(SubmissionRow).order_by(SubmissionRow.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def update_submission_status(
    session: AsyncSession, submission: SubmissionRow, status: str
) -> SubmissionRow:
    """Persist updated workflow status on a submission."""
    submission.status = status
    now_iso = dt.datetime.now(dt.UTC).isoformat()
    submission.updated_at = _parse_dt(now_iso)
    if _is_sqlite_session(session):
        session.conn.execute(
            "UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso, submission.id),
        )
        session.conn.commit()
    else:
        await session.flush()
    return submission


async def update_submission_content(
    session: AsyncSession,
    submission_id: int,
    *,
    raw_content: str,
    content_hash: str,
    actor_id: int | None = None,
    change_note: str = "Applied governance fix",
) -> SubmissionRow | None:
    """Persist updated raw_content, content_hash, and append an immutable SubmissionVersionRow."""
    if _is_sqlite_session(session):
        sub = await get_submission(session, submission_id)
        if not sub:
            return None
        now_iso = dt.datetime.now(dt.UTC).isoformat()
        session.conn.execute(
            "UPDATE submissions SET raw_content = ?, content_hash = ?, updated_at = ? WHERE id = ?",
            (raw_content, content_hash, now_iso, submission_id),
        )
        cur = session.conn.execute(
            "SELECT COALESCE(MAX(version_number), 1) FROM submission_versions "
            "WHERE submission_id = ?",
            (submission_id,),
        )
        max_ver = int(cur.fetchone()[0])
        session.conn.execute(
            """
            INSERT INTO submission_versions
            (submission_id, version_number, raw_content, content_hash,
             canon_hash, created_by, change_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                submission_id,
                max_ver + 1,
                raw_content,
                content_hash,
                sub.canon_hash,
                actor_id if actor_id is not None else sub.creator_id,
                change_note,
                now_iso,
            ),
        )
        session.conn.commit()
        sub.raw_content = raw_content
        sub.content_hash = content_hash
        sub.updated_at = _parse_dt(now_iso)
        return sub

    sub = await get_submission(session, submission_id)
    if sub:
        sub.raw_content = raw_content
        sub.content_hash = content_hash

        max_ver_res = await session.execute(
            select(func.max(SubmissionVersionRow.version_number)).where(
                SubmissionVersionRow.submission_id == submission_id
            )
        )
        current_max = max_ver_res.scalar_one_or_none() or 1
        ver = SubmissionVersionRow(
            submission_id=submission_id,
            version_number=int(current_max) + 1,
            raw_content=raw_content,
            content_hash=content_hash,
            canon_hash=sub.canon_hash,
            created_by=actor_id if actor_id is not None else sub.creator_id,
            change_note=change_note,
        )
        session.add(ver)
        await session.flush()
    return sub


async def list_submission_versions(
    session: AsyncSession, submission_id: int
) -> list[SubmissionVersionRow]:
    """Return all immutable revisions for `submission_id` in chronological order."""
    if _is_sqlite_session(session):
        cur = session.conn.execute(
            "SELECT * FROM submission_versions WHERE submission_id = ? ORDER BY version_number ASC",
            (submission_id,),
        )
        return [_row_to_version(r) for r in cur.fetchall()]
    result = await session.execute(
        select(SubmissionVersionRow)
        .where(SubmissionVersionRow.submission_id == submission_id)
        .order_by(SubmissionVersionRow.version_number.asc())
    )
    return list(result.scalars().all())


# ── Inline Comment Threads ───────────────────────────────────────────


async def create_comment(
    session: AsyncSession,
    *,
    submission_id: int,
    finding_id: int | None,
    author_id: int,
    author_name: str,
    role: str,
    body: str,
) -> SubmissionCommentRow:
    """Persist a new inline comment on a submission or specific finding card."""
    if _is_sqlite_session(session):
        now_iso = dt.datetime.now(dt.UTC).isoformat()
        cur = session.conn.execute(
            """
            INSERT INTO submission_comments
            (submission_id, finding_id, author_id, author_name, role, body, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (submission_id, finding_id, author_id, author_name, role, body, now_iso),
        )
        session.conn.commit()
        return SubmissionCommentRow(
            id=int(cur.lastrowid or 1),
            submission_id=submission_id,
            finding_id=finding_id,
            author_id=author_id,
            author_name=author_name,
            role=role,
            body=body,
            created_at=_parse_dt(now_iso),
        )
    comment = SubmissionCommentRow(
        submission_id=submission_id,
        finding_id=finding_id,
        author_id=author_id,
        author_name=author_name,
        role=role,
        body=body,
    )
    session.add(comment)
    await session.flush()
    return comment


async def list_comments_for_submission(
    session: AsyncSession,
    submission_id: int,
    *,
    finding_id: int | None = None,
) -> list[SubmissionCommentRow]:
    """Return all inline comments for `submission_id` (optionally filtered by `finding_id`)."""
    if _is_sqlite_session(session):
        if finding_id is not None:
            cur = session.conn.execute(
                "SELECT * FROM submission_comments WHERE submission_id = ? "
                "AND finding_id = ? ORDER BY id ASC",
                (submission_id, finding_id),
            )
        else:
            cur = session.conn.execute(
                "SELECT * FROM submission_comments WHERE submission_id = ? ORDER BY id ASC",
                (submission_id,),
            )
        return [_row_to_comment(r) for r in cur.fetchall()]
    stmt = select(SubmissionCommentRow).where(SubmissionCommentRow.submission_id == submission_id)
    if finding_id is not None:
        stmt = stmt.where(SubmissionCommentRow.finding_id == finding_id)
    stmt = stmt.order_by(SubmissionCommentRow.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Findings ─────────────────────────────────────────────────────────


async def save_findings(
    session: AsyncSession,
    submission_id: int,
    findings: list[Finding],
) -> None:
    """Persist a batch of domain Findings as rows."""
    if _is_sqlite_session(session):
        cur = session.conn.execute(
            "SELECT finding_id FROM findings WHERE submission_id = ? AND resolution != 'open'",
            (submission_id,),
        )
        resolved_ids = {str(r["finding_id"]) for r in cur.fetchall()}
        session.conn.execute(
            "DELETE FROM findings WHERE submission_id = ? AND resolution = 'open'",
            (submission_id,),
        )
        for f in findings:
            if str(f.id) in resolved_ids:
                continue
            session.conn.execute(
                """
                INSERT INTO findings
                (finding_id, submission_id, check_id, node_id, severity, message, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(f.id),
                    submission_id,
                    f.check_id,
                    str(f.node_id),
                    f.severity,
                    f.message,
                    f.model_dump_json(),
                ),
            )
        session.conn.commit()
        return

    existing = await session.execute(
        select(FindingRow).where(
            FindingRow.submission_id == submission_id,
            FindingRow.resolution != "open",
        )
    )
    resolved_ids = {r.finding_id for r in existing.scalars().all()}

    await session.execute(
        delete(FindingRow).where(
            FindingRow.submission_id == submission_id,
            FindingRow.resolution == "open",
        )
    )

    for f in findings:
        if f.id in resolved_ids:
            continue
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
    if _is_sqlite_session(session):
        cur = session.conn.execute(
            "SELECT * FROM findings WHERE submission_id = ? ORDER BY id ASC",
            (submission_id,),
        )
        return [_row_to_finding(r) for r in cur.fetchall()]
    result = await session.execute(
        select(FindingRow).where(FindingRow.submission_id == submission_id)
    )
    return list(result.scalars().all())


async def get_finding_by_row_id(
    session: AsyncSession,
    row_id: int,
) -> FindingRow | None:
    if _is_sqlite_session(session):
        cur = session.conn.execute("SELECT * FROM findings WHERE id = ?", (row_id,))
        row = cur.fetchone()
        return _row_to_finding(row) if row else None
    result = await session.execute(select(FindingRow).where(FindingRow.id == row_id))
    return result.scalar_one_or_none()


async def resolve_finding(
    session: AsyncSession,
    finding_row_id: int,
    *,
    resolution: str,
    resolved_by: int,
    reason: str = "",
) -> FindingRow | None:
    if _is_sqlite_session(session):
        session.conn.execute(
            "UPDATE findings SET resolution = ?, resolved_by = ?, "
            "resolution_reason = ? WHERE id = ?",
            (resolution, resolved_by, reason, finding_row_id),
        )
        session.conn.commit()
        return await get_finding_by_row_id(session, finding_row_id)
    result = await session.execute(select(FindingRow).where(FindingRow.id == finding_row_id))
    row = result.scalar_one_or_none()
    if row:
        row.resolution = resolution
        row.resolved_by = resolved_by
        row.resolution_reason = reason
        await session.flush()
    return row


async def update_finding_node_and_payload(
    session: AsyncSession,
    finding_row_id: int,
    *,
    node_id: str,
    payload_json: str,
) -> FindingRow | None:
    """Update a co-located finding's `node_id` and shifted `payload_json` after a span edit."""
    if _is_sqlite_session(session):
        session.conn.execute(
            "UPDATE findings SET node_id = ?, payload_json = ? WHERE id = ?",
            (node_id, payload_json, finding_row_id),
        )
        session.conn.commit()
        return await get_finding_by_row_id(session, finding_row_id)
    result = await session.execute(select(FindingRow).where(FindingRow.id == finding_row_id))
    row = result.scalar_one_or_none()
    if row:
        row.node_id = node_id
        row.payload_json = payload_json
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
    if _is_sqlite_session(session):
        cur = session.conn.execute(
            """
            INSERT INTO workflow_events
            (submission_id, action, from_status, to_status, actor_id, comment,
             prev_hash, event_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                submission_id,
                action,
                from_status,
                to_status,
                actor_id,
                comment,
                prev_hash,
                event_hash,
                created_at,
            ),
        )
        session.conn.commit()
        return WorkflowEventRow(
            id=int(cur.lastrowid or 1),
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
    if _is_sqlite_session(session):
        cur = session.conn.execute(
            "SELECT * FROM workflow_events WHERE submission_id = ? ORDER BY id ASC",
            (submission_id,),
        )
        return [_row_to_event(r) for r in cur.fetchall()]
    result = await session.execute(
        select(WorkflowEventRow)
        .where(WorkflowEventRow.submission_id == submission_id)
        .order_by(WorkflowEventRow.id)
    )
    return list(result.scalars().all())


async def get_findings_for_canon(session: AsyncSession, canon_id: str) -> list[FindingRow]:
    """Retrieve all finding rows across all submissions governed by canon_id."""
    if _is_sqlite_session(session):
        cur = session.conn.execute(
            """
            SELECT f.* FROM findings f
            JOIN submissions s ON f.submission_id = s.id
            WHERE s.canon_id = ?
            ORDER BY f.id ASC
            """,
            (canon_id,),
        )
        return [_row_to_finding(r) for r in cur.fetchall()]
    result = await session.execute(
        select(FindingRow)
        .join(SubmissionRow, FindingRow.submission_id == SubmissionRow.id)
        .where(SubmissionRow.canon_id == canon_id)
    )
    return list(result.scalars().all())
