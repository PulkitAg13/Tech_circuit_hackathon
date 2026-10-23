"""App settings via pydantic-settings. Single source of truth for config."""

from __future__ import annotations

from pathlib import Path

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings  # type: ignore[no-redef]


class Settings(BaseSettings):
    model_config = {"env_prefix": "CANONGATE_", "env_file": ".env", "extra": "ignore"}

    if not hasattr(BaseSettings, "model_config"):

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
    cors_origins: list[str] = ["http://localhost:5173"]

    # Auth (walking skeleton: simple shared secret)
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
