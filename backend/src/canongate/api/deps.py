"""FastAPI dependencies: session, current user, canon loader."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from canongate.canon.loader import load_canon
from canongate.domain.canon import Canon
from canongate.settings import Settings
from canongate.store.db import async_session
from canongate.store.repos import get_user_by_username
from canongate.store.tables import UserRow

_settings = Settings()

# ── Canon cache (loaded once per server start) ───────────────────────

_canon_cache: dict[str, Canon] = {}


def _load_all_canons() -> None:
    """Scan the canons directory and cache all Canon files."""
    canon_dir = _settings.canon_dir
    if not canon_dir.exists():
        return
    for p in canon_dir.glob("*.yaml"):
        canon = load_canon(p)
        _canon_cache[canon.id] = canon
    for p in canon_dir.glob("*.yml"):
        canon = load_canon(p)
        _canon_cache[canon.id] = canon


def get_canon(canon_id: str) -> Canon:
    """Get a cached Canon by id. Raises 404 if not found."""
    if not _canon_cache:
        _load_all_canons()
    canon = _canon_cache.get(canon_id)
    if not canon:
        raise HTTPException(status_code=404, detail=f"Canon {canon_id!r} not found")
    return canon


def list_canon_ids() -> list[str]:
    if not _canon_cache:
        _load_all_canons()
    return list(_canon_cache.keys())


# ── Database session ─────────────────────────────────────────────────


async def get_session() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session, session.begin():
        yield session  # type: ignore[misc]


SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ── JWT Auth ─────────────────────────────────────────────────────────


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from None


def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=_settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


async def get_current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> UserRow:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization format")

    claims = _decode_token(token)
    user = await get_user_by_username(session, claims["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


CurrentUser = Annotated[UserRow, Depends(get_current_user)]
