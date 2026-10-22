"""Auth routes: register & login (walking skeleton: bcrypt-free for speed)."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from canongate.api.deps import SessionDep, create_token
from canongate.store.repos import create_user, get_user_by_username

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_password(pw: str) -> str:
    """Walking skeleton: simple SHA-256. Replace with bcrypt for production."""
    return hashlib.sha256(pw.encode()).hexdigest()


class RegisterRequest(BaseModel):
    username: str
    display_name: str = ""
    role: str = "creator"
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    username: str
    role: str


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, session: SessionDep) -> TokenResponse:
    existing = await get_user_by_username(session, req.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    if req.role not in ("creator", "reviewer", "admin"):
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    user = await create_user(
        session,
        username=req.username,
        display_name=req.display_name or req.username,
        role=req.role,
        password_hash=_hash_password(req.password),
    )
    token = create_token(user.username, user.role)
    return TokenResponse(token=token, username=user.username, role=user.role)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, session: SessionDep) -> TokenResponse:
    user = await get_user_by_username(session, req.username)
    if not user or user.password_hash != _hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user.username, user.role)
    return TokenResponse(token=token, username=user.username, role=user.role)
