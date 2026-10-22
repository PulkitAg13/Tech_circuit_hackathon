"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from canongate.settings import Settings
from canongate.store import init_db

_settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables + warm canon cache."""
    await init_db()
    # Warm the canon cache
    from canongate.api.deps import _load_all_canons

    _load_all_canons()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="CanonGate",
        description="Pre-publication brand & claim governance platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from canongate.api.routes.auth import router as auth_router
    from canongate.api.routes.canons import router as canons_router
    from canongate.api.routes.submissions import router as submissions_router

    app.include_router(auth_router, prefix="/api")
    app.include_router(submissions_router, prefix="/api")
    app.include_router(canons_router, prefix="/api")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
