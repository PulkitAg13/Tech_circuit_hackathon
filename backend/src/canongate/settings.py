"""App settings via pydantic-settings. Single source of truth for config."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "CANONGATE_", "env_file": ".env"}

    # Database
    db_url: str = "sqlite+aiosqlite:///./canongate.db"

    # Canon
    canon_dir: Path = Path("canons")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]

    # Auth (walking skeleton: simple shared secret)
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h
