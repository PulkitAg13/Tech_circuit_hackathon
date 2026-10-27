"""Database engine & session factory for async SQLAlchemy with stdlib sqlite3 fallback."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from canongate.settings import Settings
from canongate.store.tables import HAS_SQLALCHEMY, Base

_settings = Settings()

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'creator',
    password_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT 'Untitled',
    raw_content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    canon_id TEXT NOT NULL,
    canon_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    creator_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS submission_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    raw_content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    canon_hash TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    change_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT NOT NULL,
    submission_id INTEGER NOT NULL,
    check_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    severity INTEGER NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    resolution TEXT NOT NULL DEFAULT 'open',
    resolution_reason TEXT NOT NULL DEFAULT '',
    resolved_by INTEGER
);
CREATE TABLE IF NOT EXISTS submission_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    finding_id INTEGER,
    author_id INTEGER NOT NULL,
    author_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'creator',
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS workflow_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    actor_id INTEGER NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    prev_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_submissions_canon_id ON submissions(canon_id);
CREATE INDEX IF NOT EXISTS idx_submissions_creator_id ON submissions(creator_id);
CREATE INDEX IF NOT EXISTS idx_findings_submission_id ON findings(submission_id);
CREATE INDEX IF NOT EXISTS idx_workflow_events_submission_id ON workflow_events(submission_id);
CREATE INDEX IF NOT EXISTS idx_sub_versions_sub_id ON submission_versions(submission_id);
CREATE INDEX IF NOT EXISTS idx_sub_comments_sub_id ON submission_comments(submission_id);
INSERT OR IGNORE INTO users (id, username, display_name, role, password_hash)
VALUES (
    1, 'creative_lead', 'Agency Creative Lead', 'creator',
    '3d931af2d93df3e444192ad842316b5a115db2f46bef9e975ef8f031701724c8'
);
UPDATE users
SET password_hash = '3d931af2d93df3e444192ad842316b5a115db2f46bef9e975ef8f031701724c8'
WHERE username = 'creative_lead';
"""


def _resolve_sqlite_path(db_url: str) -> str:
    if ":memory:" in db_url:
        return ":memory:"
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if db_url.startswith(prefix):
            raw = db_url[len(prefix) :]
            return str(Path(raw))
    return "canongate.db"


class _TxContext:
    def __init__(self, session: SqliteAsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> _TxContext:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None:
            self._session.conn.commit()
        else:
            self._session.conn.rollback()


class SqliteAsyncSession:
    """Async session wrapper over stdlib `sqlite3.Connection` when SQLAlchemy is unavailable."""

    is_sqlite_fallback: bool = True

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    async def __aenter__(self) -> SqliteAsyncSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None:
            self.conn.commit()

    def begin(self) -> _TxContext:
        return _TxContext(self)

    async def flush(self) -> None:
        self.conn.commit()

    async def commit(self) -> None:
        self.conn.commit()


_shared_sqlite_conn: sqlite3.Connection | None = None


def _get_sqlite_conn() -> sqlite3.Connection:
    global _shared_sqlite_conn
    if _shared_sqlite_conn is None:
        db_path = _resolve_sqlite_path(_settings.db_url)
        try:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.executescript(_SQLITE_DDL)
            conn.commit()
            _shared_sqlite_conn = conn
        except sqlite3.OperationalError:
            tmp_path = (
                str(Path("/tmp") / Path(db_path).name) if db_path != ":memory:" else ":memory:"
            )
            conn = sqlite3.connect(tmp_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.executescript(_SQLITE_DDL)
            conn.commit()
            _shared_sqlite_conn = conn
    return _shared_sqlite_conn


if HAS_SQLALCHEMY:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(_settings.db_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def init_db() -> None:
        """Create all tables. Idempotent."""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

else:
    AsyncSession = SqliteAsyncSession  # type: ignore[misc,assignment]
    engine = None  # type: ignore[assignment]

    def async_session() -> SqliteAsyncSession:  # type: ignore[misc]
        return SqliteAsyncSession(_get_sqlite_conn())

    async def init_db() -> None:
        """Create all tables in SQLite fallback mode. Idempotent."""
        conn = _get_sqlite_conn()
        conn.executescript(_SQLITE_DDL)
        conn.commit()
