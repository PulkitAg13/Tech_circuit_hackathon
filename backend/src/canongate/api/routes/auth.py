"""Auth routes: register, login, current user profile, and role switching."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from canongate.api.deps import CurrentUser, SessionDep, create_token
from canongate.store import repos
from canongate.store.repos import create_user, get_user_by_username

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_password(pw: str) -> str:
    """SHA-256 password digest for zero-config container deployment."""
    return hashlib.sha256(pw.encode()).hexdigest()


class RegisterRequest(BaseModel):
    username: str
    display_name: str = ""
    role: str = "creator"
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class SwitchRoleRequest(BaseModel):
    role: str


class TokenResponse(BaseModel):
    token: str
    username: str
    display_name: str = ""
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
    return TokenResponse(
        token=token,
        username=user.username,
        display_name=user.display_name or user.username,
        role=user.role,
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, session: SessionDep) -> TokenResponse:
    user = await get_user_by_username(session, req.username)
    if not user or user.password_hash != _hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user.username, user.role)
    return TokenResponse(
        token=token,
        username=user.username,
        display_name=user.display_name or user.username,
        role=user.role,
    )


@router.get("/me", response_model=TokenResponse)
async def get_me(current_user: CurrentUser) -> TokenResponse:
    token = create_token(current_user.username, current_user.role)
    return TokenResponse(
        token=token,
        username=current_user.username,
        display_name=current_user.display_name or current_user.username,
        role=current_user.role,
    )


@router.post("/switch-role", response_model=TokenResponse)
async def switch_role(
    req: SwitchRoleRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> TokenResponse:
    """Switch the active RBAC workspace role for the signed-in user without changing identity."""
    if req.role not in ("creator", "reviewer", "admin"):
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    if hasattr(repos, "update_user_role"):
        await repos.update_user_role(session, current_user, req.role)
    else:
        current_user.role = req.role
        if hasattr(session, "add"):
            session.add(current_user)
        if hasattr(session, "flush"):
            await session.flush()

    token = create_token(current_user.username, current_user.role)
    return TokenResponse(
        token=token,
        username=current_user.username,
        display_name=current_user.display_name or current_user.username,
        role=current_user.role,
    )
