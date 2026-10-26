"""FastAPI application factory."""

from __future__ import annotations

import hashlib
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
            existing = await get_user_by_username(session, uname)
            if not existing:
                pw_hash = hashlib.sha256(pw.encode()).hexdigest()
                await create_user(
                    session,
                    username=uname,
                    display_name=dname,
                    role=role,
                    password_hash=pw_hash,
                )


_LEGACY_DEMO_TITLES = (
    "Diwali Instant Digital Loan Campaign Bundle",
    "AyurGlow Curcumin Gold Elixir Landing Page",
    "RBI 2025 KFS & CCPA Pre-Flight — Instant Personal Loan Bundle",
)


async def _purge_legacy_demo_submissions() -> None:
    """Remove any leftover auto-seeded demo bundles from older database files."""
    from canongate.store import repos

    async with async_session() as session, session.begin():
        subs = await repos.list_submissions(session, limit=200)
        for s in subs:
            if s.title in _LEGACY_DEMO_TITLES and hasattr(repos, "delete_submission"):
                await repos.delete_submission(session, s.id)


async def _startup_init() -> None:
    await init_db()
    await _seed_default_users()
    await _purge_legacy_demo_submissions()
    from canongate.api.deps import _load_all_canons

    _load_all_canons()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables, seed starter accounts, and warm canon cache."""
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
