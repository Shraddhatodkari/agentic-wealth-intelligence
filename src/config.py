"""
Centralized configuration, loaded from environment variables and a
local .env file in development. Nothing in this codebase should read
os.environ directly outside this module - every setting is declared
here once, typed, with a documented default.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always resolve .env relative to the project root, not the current
# working directory. This makes configuration reliable from Streamlit,
# pytest, CLI commands, Docker, and other entry points.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load environment before Settings() is instantiated.
load_dotenv(ENV_FILE, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        extra="ignore",
    )

    # LLM
    llm_mode: str = "mock"  # "mock" | "live" | "ollama"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    ollama_model: str = "phi4-mini"
    ollama_url: str = "http://localhost:11434/api/generate"

    # API auth - "key:role" pairs, comma-separated.
    # Roles: "admin" > "analyst" > "viewer".
    api_keys: str = "dev-local-key:admin"

    # Rate limiting (requests per minute per API key)
    rate_limit_per_minute: int = 30

    # Logging
    log_level: str = "INFO"

    # Embeddings
    embedding_mode: str = "hashing"

    # Required by SEC for real EDGAR API calls.
    sec_user_agent: str = ""

    # Caching
    cache_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"

    # Async job queue
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    @property
    def api_key_roles(self) -> dict:
        """Map each configured API key to its role."""
        roles = {}

        for pair in self.api_keys.split(","):
            pair = pair.strip()

            if not pair:
                continue

            if ":" in pair:
                key, role = pair.split(":", 1)
            else:
                key, role = pair, "viewer"

            roles[key.strip()] = role.strip()

        return roles

    @property
    def valid_api_keys(self) -> List[str]:
        return list(self.api_key_roles.keys())


settings = Settings()
