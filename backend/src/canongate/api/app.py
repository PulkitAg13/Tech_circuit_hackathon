"""FastAPI application factory."""

from __future__ import annotations

import hashlib
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from canongate.settings import Settings
from canongate.store import init_db
from canongate.store.db import async_session
from canongate.store.repos import create_user, get_user_by_username

_settings = Settings()

_DEFAULT_DEMO_USERS = (
    ("creative_lead", "Agency Creative Lead", "creator", "demoPassword123!"),
    ("brand_manager", "Brand Governance Manager", "reviewer", "demoPassword123!"),
    ("legal_counsel", "Authorised Legal Reviewer", "admin", "demoPassword123!"),
    ("pulkit_manager", "Pulkit Agrawal (Brand Manager)", "reviewer", "demoPassword123!"),
    ("aritra_legal", "Aritra Mahanty (Legal Reviewer)", "admin", "demoPassword123!"),
)


async def _seed_default_users() -> None:
    """Ensure starter evaluation accounts exist on a fresh database."""
    async with async_session() as session, session.begin():
        for uname, dname, role, pw in _DEFAULT_DEMO_USERS:
            pw_hash = hashlib.sha256(pw.encode()).hexdigest()
            existing = await get_user_by_username(session, uname)
            if not existing:
                await create_user(
                    session,
                    username=uname,
                    display_name=dname,
                    role=role,
                    password_hash=pw_hash,
                )
            elif existing.password_hash != pw_hash:
                existing.password_hash = pw_hash
                if getattr(session, "is_sqlite_fallback", False):
                    session.conn.execute(
                        "UPDATE users SET password_hash = ? WHERE username = ?",
                        (pw_hash, uname),
                    )


_LEGACY_DEMO_TITLES_LOWER: frozenset[str] = frozenset(
    t.lower()
    for t in (
        "Diwali Instant Digital Loan Campaign Bundle",
        "AyurGlow Curcumin Gold Elixir Landing Page",
        "AyurGlow Curcumin Gold Elixir",
        "AyurGlow Curcumin Gold Elixir Launch",
        "RBI 2025 KFS & CCPA Pre-Flight — Instant Personal Loan Bundle",
        "RBI 2025 KFS & CCPA Pre-Flight · Instant Personal Loan Bundle",
        "Clean Acme Announcement",
        "Minor Tone Drift",
        "QuickLoan Festival Credit Campaign",
        "QuickLoan Diwali Festival Campaign",
        "Acme QuickLoan Diwali Festival Campaign",
        "CloudScale Enterprise Tier Release",
        "Enterprise Cloud Launch Landing Page",
        "Acme Cloud Enterprise Launch Landing Page",
        "Duplicate & Table Alignment Test",
        "Monsoon Digital Lending Campaign",
        "Monsoon KFS Campaign",
        "Monsoon Instant Personal Loan Banner",
        "Instant Personal Loan Flash Offer",
        "Curcumin Gold Festival Offer",
        "Curcumin Gold Festival Bundle",
        "Hero Banner CSS Token Check",
        "Approved KFS Personal Credit Disclosure",
        "Brand Deck & Pricing Spec Check",
        "Q3 Instant Personal Loan Campaign",
        "MCP Agent Loan Ad Audit",
        "P1-P6 Full Feature Test",
        "E2E Verification Campaign",
        "nutra_landing.html",
        "promo_1080p.png",
        "lending_offer.md",
        "Test",
        "Test Sub",
        "Test Campaign",
    )
)

_TOY_OR_TEST_TITLE_RE = re.compile(
    r"^(?:asset_\d+\.(?:md|txt|html|png|jpg|pdf|docx)|"
    r"nutra_landing\.html|promo_1080p\.png|lending_offer\.md|"
    r"test(?:[\s_-].*)?)$",
    re.IGNORECASE,
)


def is_toy_or_test_submission(title: str) -> bool:
    """Return True if a submission title belongs to a toy/demo preset or test-suite fixture."""
    clean = (title or "").strip()
    if not clean:
        return False
    if clean.lower() in _LEGACY_DEMO_TITLES_LOWER:
        return True
    return bool(_TOY_OR_TEST_TITLE_RE.match(clean))


async def _purge_legacy_demo_submissions() -> None:
    """Remove any leftover auto-seeded demo bundles or test-suite fixtures from database files."""
    from canongate.store import repos

    async with async_session() as session, session.begin():
        subs = await repos.list_submissions(session, limit=5000)
        for s in subs:
            if is_toy_or_test_submission(s.title) and hasattr(repos, "delete_submission"):
                await repos.delete_submission(session, s.id)


async def _startup_init() -> None:
    await init_db()
    await _seed_default_users()
    await _purge_legacy_demo_submissions()
    from canongate.api.deps import _load_all_canons

    _load_all_canons()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables, seed starter accounts, purge toy/test ads, and warm canon cache."""
    await _startup_init()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="CanonGate",
        description="Pre-publication brand & claim governance platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.on_event("startup")
    async def _on_startup() -> None:
        await _startup_init()

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.cors_origins,
        allow_origin_regex=r"^https://.*\.onrender\.com$|^https://.*\.github\.io$|^https://.*\.loca\.lt$|^http://localhost:.*$|^http://127\.0\.0\.1:.*$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from canongate.api.routes.auth import router as auth_router
    from canongate.api.routes.canons import router as canons_router
    from canongate.api.routes.gate import router as gate_router
    from canongate.api.routes.submissions import router as submissions_router

    app.include_router(auth_router, prefix="/api")
    app.include_router(submissions_router, prefix="/api")
    app.include_router(canons_router, prefix="/api")
    app.include_router(gate_router, prefix="/api")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
