"""FastAPI dependencies: session, current user, canon loader & registry."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import inspect
import json
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin

import fastapi as _fastapi
import fastapi.dependencies.utils as _fdu
from fastapi import Depends, Header, HTTPException
from fastapi import params as _fparams

from canongate.canon.impact import _canon_to_yaml
from canongate.canon.loader import load_canon
from canongate.domain.canon import Canon
from canongate.settings import Settings
from canongate.store.db import async_session
from canongate.store.repos import get_user_by_username

try:
    import jwt as _pyjwt
except ImportError:
    _pyjwt = None  # type: ignore[assignment]

_orig_get_typed_sig = _fdu.get_typed_signature


def _annotated_aware_typed_signature(call: Any) -> inspect.Signature:
    sig = _orig_get_typed_sig(call)
    new_params = []
    for p in sig.parameters.values():
        if p.default is inspect.Parameter.empty and get_origin(p.annotation) is Annotated:
            args = get_args(p.annotation)
            for meta in args[1:]:
                if isinstance(meta, _fparams.Depends):
                    p = p.replace(annotation=args[0], default=meta)
                    break
        new_params.append(p)
    return sig.replace(parameters=new_params)


_fver = tuple(int(x) for x in getattr(_fastapi, "__version__", "0.0").split(".")[:2])
if _fver < (0, 95):
    _fdu.get_typed_signature = _annotated_aware_typed_signature

_settings = Settings()

# ── Canon cache (loaded once per server start) ───────────────────────

_canon_cache: dict[str, Canon] = {}


def _resolve_canon_dir() -> Path:
    canon_dir = _settings.canon_dir
    if canon_dir.exists():
        return canon_dir
    alt_dir = Path(__file__).resolve().parents[4] / "canons"
    if alt_dir.exists():
        return alt_dir
    return canon_dir


def _load_all_canons() -> None:
    """Scan the canons directory and cache all Canon files."""
    canon_dir = _resolve_canon_dir()
    if not canon_dir.exists():
        return
    for p in sorted(canon_dir.glob("*.yaml")):
        canon = load_canon(p)
        _canon_cache[canon.id] = canon
    for p in sorted(canon_dir.glob("*.yml")):
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


def register_canon(canon: Canon, *, persist_yaml: bool = False) -> Path | None:
    """Register a compiled or revised `Canon` in the live cache and optionally write YAML."""
    if not _canon_cache:
        _load_all_canons()
    _canon_cache[canon.id] = canon
    if persist_yaml:
        canon_dir = _resolve_canon_dir()
        canon_dir.mkdir(parents=True, exist_ok=True)
        out_path = canon_dir / f"{canon.id}.yaml"
        out_path.write_text(_canon_to_yaml(canon), encoding="utf-8")
        return out_path
    return None


def list_canon_ids() -> list[str]:
    if not _canon_cache:
        _load_all_canons()
    return list(_canon_cache.keys())


# ── Database session ─────────────────────────────────────────────────


async def get_session():
    async with async_session() as session, session.begin():
        yield session  # type: ignore[misc]


SessionDep = Annotated[Any, Depends(get_session)]


# ── JWT Auth (PyJWT with RFC 7519 HS256 stdlib fallback) ─────────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _encode_hs256_jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    body = dict(payload)
    if isinstance(body.get("exp"), dt.datetime):
        body["exp"] = int(body["exp"].timestamp())
    p_b64 = _b64url_encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"


def _decode_hs256_jwt(token: str, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT token")
    h_b64, p_b64, s_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = _b64url_decode(s_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid JWT signature")
    claims = json.loads(_b64url_decode(p_b64).decode("utf-8"))
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and dt.datetime.now(dt.UTC).timestamp() > exp:
        raise ValueError("Token has expired")
    return claims


def _decode_token(token: str) -> dict[str, Any]:
    if _pyjwt is not None:
        try:
            return _pyjwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
        except _pyjwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from None
    try:
        return _decode_hs256_jwt(token, _settings.jwt_secret)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from None


def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=_settings.jwt_expire_minutes),
    }
    if _pyjwt is not None:
        return _pyjwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)
    return _encode_hs256_jwt(payload, _settings.jwt_secret)


async def get_current_user(
    session: SessionDep,
    authorization: str | None = Header(default=None),
):
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


CurrentUser = Annotated[Any, Depends(get_current_user)]
