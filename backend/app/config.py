"""Application settings, loaded from environment variables / .env file."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name: str = "MedOrchestra"
    hospital_name: str = os.getenv("HOSPITAL_NAME", "CityCare Multispeciality Hospital")

    # Database: SQLite for local demo, PostgreSQL in production (docker-compose).
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'hospital.db').as_posix()}")

    # Auth
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production-medorchestra-secret")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))

    # LLM (optional). Without a key the system uses its local NLP pipeline.
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    llm_model: str = os.getenv("LLM_MODEL", "claude-opus-5")
    llm_enabled: bool = _bool("LLM_ENABLED", True)
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))

    # Orchestrator
    agent_step_delay: float = float(os.getenv("AGENT_STEP_DELAY", "0.35"))  # visual pacing for live trace

    # Simulation
    simulation_interval: float = float(os.getenv("SIMULATION_INTERVAL", "8"))

    cors_origins: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173").split(",")
        if o.strip()
    ]

    @property
    def llm_available(self) -> bool:
        return self.llm_enabled and bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
