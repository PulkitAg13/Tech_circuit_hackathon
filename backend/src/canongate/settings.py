"""App settings via pydantic-settings with Pydantic v1/v2 compatibility."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from pydantic_settings import BaseSettings as _BaseSettings
except Exception:
    try:
        from pydantic import BaseSettings as _BaseSettings  # type: ignore[no-redef]
    except Exception:
        from pydantic import BaseModel as _BaseSettings  # type: ignore[assignment]


class Settings(_BaseSettings):
    model_config = {"env_prefix": "CANONGATE_", "env_file": ".env", "extra": "ignore"}

    if not hasattr(_BaseSettings, "model_config"):

        class Config:
            env_prefix = "CANONGATE_"
            env_file = ".env"
            extra = "ignore"

    # Database
    db_url: str = "sqlite+aiosqlite:///./canongate.db"

    # Canon
    canon_dir: Path = Path("canons")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h

    # Multi-Provider LLM Configuration (for complex tables & Pipeline A Canon compilation)
    # Supported values: "auto" | "gemini" | "openai" | "groq" | "ollama" | "none"
    llm_provider: str = "auto"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    llm_timeout_s: float = 15.0

    def __init__(self, **values: Any) -> None:
        env_overrides: dict[str, Any] = {}
        fields = getattr(self.__class__, "model_fields", None) or getattr(
            self.__class__, "__fields__", {}
        )
        for field_name in fields:
            env_key = f"CANONGATE_{field_name.upper()}"
            if env_key in os.environ and field_name not in values:
                env_overrides[field_name] = os.environ[env_key]
        super().__init__(**{**env_overrides, **values})
