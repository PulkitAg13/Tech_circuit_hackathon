"""App settings via pydantic-settings with Pydantic v1/v2 compatibility."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    from pydantic_settings import BaseSettings as _BaseSettings
except Exception:
    try:
        from pydantic import BaseSettings as _BaseSettings  # type: ignore[no-redef]
    except Exception:
        from pydantic import BaseModel as _BaseSettings  # type: ignore[assignment]


def _load_env_file() -> None:
    if (
        os.environ.get("PYTEST_CURRENT_TEST")
        or "pytest" in sys.modules
        or any("pytest" in arg for arg in sys.argv)
    ):
        return
    candidates = (
        Path(".env"),
        Path("../.env"),
        Path(__file__).resolve().parents[4] / ".env",
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
            except Exception:
                pass
            break


_load_env_file()


class Settings(_BaseSettings):
    model_config = {"env_prefix": "CANONGATE_", "env_file": ".env", "extra": "ignore"}

    if not hasattr(_BaseSettings, "model_config"):

        class Config:
            env_prefix = "CANONGATE_"
            env_file = ".env"
            extra = "ignore"

    # Database (isolate pytest runs so test suites never pollute ./canongate.db)
    db_url: str = (
        "sqlite+aiosqlite:////tmp/canongate_pytest.db"
        if (
            os.environ.get("PYTEST_CURRENT_TEST")
            or "pytest" in sys.modules
            or any("pytest" in arg for arg in sys.argv)
        )
        else "sqlite+aiosqlite:///./canongate.db"
    )

    # Canon
    canon_dir: Path = Path("canons")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "https://meerpi.github.io",
        "https://canongate-web.onrender.com",
    ]

    # Auth & Cryptographic Ledger Signing
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h

    # Voyage AI Dense Embeddings (Voyage 4 series) & Instruction-Following Reranker NLI
    voyage_api_key: str = ""
    voyage_base_url: str = "https://api.voyageai.com/v1"
    voyage_embed_model: str = "voyage-4-lite"
    voyage_embed_dim: int = 512
    voyage_rerank_model: str = "rerank-2.5"
    voyage_rerank_fallback_model: str = "rerank-2.5-lite"
    voyage_timeout_s: float = 3.5

    # Multi-Provider LLM Configuration (for complex tables & Pipeline A Canon compilation)
    # Supported values: "auto" | "gemini" | "openai" | "groq" | "ollama" | "none"
    llm_provider: str = "auto"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
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
            fallback_env_key = field_name.upper()
            raw_val: Any = None
            if env_key in os.environ and field_name not in values:
                raw_val = os.environ[env_key]
            elif (
                fallback_env_key in os.environ
                and field_name not in values
                and field_name.startswith(("voyage_", "gemini_", "openai_"))
            ):
                raw_val = os.environ[fallback_env_key]
            if raw_val is not None:
                if (
                    isinstance(raw_val, str)
                    and raw_val.startswith(("[", "{"))
                    and raw_val.endswith(("]", "}"))
                ):
                    try:
                        import json

                        raw_val = json.loads(raw_val)
                    except Exception:
                        pass
                env_overrides[field_name] = raw_val
        super().__init__(**{**env_overrides, **values})


settings = Settings()
