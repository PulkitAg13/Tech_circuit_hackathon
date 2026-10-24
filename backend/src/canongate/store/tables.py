"""SQLAlchemy table definitions for CanonGate with zero-dependency dataclass fallback.

Tables:
- submissions: content bundles submitted for review
- submission_versions: immutable revision history for each submission
- findings: findings produced by checks (linked to submissions)
- submission_comments: inline comment threads on submissions and findings
- workflow_events: hash-chained audit log
- users: user table for JWT role-based auth
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

try:
    from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


if HAS_SQLALCHEMY:

    class Base(DeclarativeBase):
        pass

    class UserRow(Base):
        __tablename__ = "users"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
        display_name: Mapped[str] = mapped_column(String(128), default="")
        role: Mapped[str] = mapped_column(String(32), default="creator")
        password_hash: Mapped[str] = mapped_column(String(256), default="")
        created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    class SubmissionRow(Base):
        __tablename__ = "submissions"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        title: Mapped[str] = mapped_column(String(256), default="Untitled")
        raw_content: Mapped[str] = mapped_column(Text, nullable=False)
        content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
        canon_id: Mapped[str] = mapped_column(String(64), nullable=False)
        canon_hash: Mapped[str] = mapped_column(String(64), nullable=False)
        status: Mapped[str] = mapped_column(String(32), default="draft")
        creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
        created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
        updated_at: Mapped[dt.datetime] = mapped_column(
            DateTime, server_default=func.now(), onupdate=func.now()
        )

        findings: Mapped[list[FindingRow]] = relationship(
            back_populates="submission", cascade="all, delete-orphan"
        )
        events: Mapped[list[WorkflowEventRow]] = relationship(
            back_populates="submission", cascade="all, delete-orphan"
        )
        versions: Mapped[list[SubmissionVersionRow]] = relationship(
            back_populates="submission", cascade="all, delete-orphan"
        )
        comments: Mapped[list[SubmissionCommentRow]] = relationship(
            back_populates="submission", cascade="all, delete-orphan"
        )

    class SubmissionVersionRow(Base):
        __tablename__ = "submission_versions"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        submission_id: Mapped[int] = mapped_column(
            Integer, ForeignKey("submissions.id"), nullable=False
        )
        version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
        raw_content: Mapped[str] = mapped_column(Text, nullable=False)
        content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
        canon_hash: Mapped[str] = mapped_column(String(64), nullable=False)
        created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
        change_note: Mapped[str] = mapped_column(Text, default="")
        created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

        submission: Mapped[SubmissionRow] = relationship(back_populates="versions")

    class FindingRow(Base):
        __tablename__ = "findings"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        finding_id: Mapped[str] = mapped_column(String(32), nullable=False)
        submission_id: Mapped[int] = mapped_column(
            Integer, ForeignKey("submissions.id"), nullable=False
        )
        check_id: Mapped[str] = mapped_column(String(64), nullable=False)
        node_id: Mapped[str] = mapped_column(String(64), nullable=False)
        severity: Mapped[int] = mapped_column(Integer, nullable=False)
        message: Mapped[str] = mapped_column(Text, nullable=False)
        payload_json: Mapped[str] = mapped_column(Text, nullable=False)
        resolution: Mapped[str] = mapped_column(String(32), default="open")
        resolution_reason: Mapped[str] = mapped_column(Text, default="")
        resolved_by: Mapped[int | None] = mapped_column(
            Integer, ForeignKey("users.id"), nullable=True
        )

        submission: Mapped[SubmissionRow] = relationship(back_populates="findings")

    class SubmissionCommentRow(Base):
        __tablename__ = "submission_comments"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        submission_id: Mapped[int] = mapped_column(
            Integer, ForeignKey("submissions.id"), nullable=False
        )
        finding_id: Mapped[int | None] = mapped_column(
            Integer, ForeignKey("findings.id"), nullable=True
        )
        author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
        author_name: Mapped[str] = mapped_column(String(128), default="")
        role: Mapped[str] = mapped_column(String(32), default="creator")
        body: Mapped[str] = mapped_column(Text, nullable=False)
        created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

        submission: Mapped[SubmissionRow] = relationship(back_populates="comments")

    class WorkflowEventRow(Base):
        __tablename__ = "workflow_events"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        submission_id: Mapped[int] = mapped_column(
            Integer, ForeignKey("submissions.id"), nullable=False
        )
        action: Mapped[str] = mapped_column(String(32), nullable=False)
        from_status: Mapped[str] = mapped_column(String(32), nullable=False)
        to_status: Mapped[str] = mapped_column(String(32), nullable=False)
        actor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
        comment: Mapped[str] = mapped_column(Text, default="")
        prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
        event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
        created_at: Mapped[str] = mapped_column(String(64), nullable=False)

        submission: Mapped[SubmissionRow] = relationship(back_populates="events")

else:

    class Base:  # type: ignore[no-redef]
        pass

    @dataclass
    class UserRow:  # type: ignore[no-redef]
        id: int = 0
        username: str = ""
        display_name: str = ""
        role: str = "creator"
        password_hash: str = ""
        created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))

    @dataclass
    class SubmissionRow:  # type: ignore[no-redef]
        id: int = 0
        title: str = "Untitled"
        raw_content: str = ""
        content_hash: str = ""
        canon_id: str = ""
        canon_hash: str = ""
        status: str = "draft"
        creator_id: int = 0
        created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
        updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))

    @dataclass
    class SubmissionVersionRow:  # type: ignore[no-redef]
        id: int = 0
        submission_id: int = 0
        version_number: int = 1
        raw_content: str = ""
        content_hash: str = ""
        canon_hash: str = ""
        created_by: int = 0
        change_note: str = ""
        created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))

    @dataclass
    class FindingRow:  # type: ignore[no-redef]
        id: int = 0
        finding_id: str = ""
        submission_id: int = 0
        check_id: str = ""
        node_id: str = ""
        severity: int = 0
        message: str = ""
        payload_json: str = ""
        resolution: str = "open"
        resolution_reason: str = ""
        resolved_by: int | None = None

    @dataclass
    class SubmissionCommentRow:  # type: ignore[no-redef]
        id: int = 0
        submission_id: int = 0
        finding_id: int | None = None
        author_id: int = 0
        author_name: str = ""
        role: str = "creator"
        body: str = ""
        created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))

    @dataclass
    class WorkflowEventRow:  # type: ignore[no-redef]
        id: int = 0
        submission_id: int = 0
        action: str = ""
        from_status: str = ""
        to_status: str = ""
        actor_id: int = 0
        comment: str = ""
        prev_hash: str = ""
        event_hash: str = ""
        created_at: str = ""
