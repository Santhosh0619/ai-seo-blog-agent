"""Settings from the project-root .env. Secrets are never logged."""
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
log = logging.getLogger("seo.config")

PRODUCT_NAME = "Rankwise"  # one constant: change it here (and frontend/src/brand.js) to rename the product
PLACEHOLDERS = {"", "your_gemini_api_key_here", "your_key_here", "changeme"}


def _e(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class Settings:
    gemini_api_key: str = field(default_factory=lambda: _e("GEMINI_API_KEY"))
    llm_model: str = field(default_factory=lambda: _e("LLM_MODEL", "gemini-3.5-flash"))
    # tried in order when the main model is overloaded (503) or its free quota is used up (429)
    fallback_models: list[str] = field(default_factory=lambda: [m.strip() for m in _e("LLM_FALLBACK_MODELS", "gemini-3.8-flash,gemini-3.1-flash-lite").split(",") if m.strip()])
    image_model: str = field(default_factory=lambda: _e("IMAGE_MODEL", "gemini-2.5-flash-image"))
    images_enabled: bool = field(default_factory=lambda: _e("IMAGES_ENABLED", "true").lower() != "false")
    pexels_api_key: str = field(default_factory=lambda: _e("PEXELS_API_KEY"))
    pixabay_api_key: str = field(default_factory=lambda: _e("PIXABAY_API_KEY"))
    database_url: str = field(default_factory=lambda: _e("DATABASE_URL"))
    db_host: str = field(default_factory=lambda: _e("DB_HOST", "127.0.0.1"))
    db_port: str = field(default_factory=lambda: _e("DB_PORT", "5434"))
    db_name: str = field(default_factory=lambda: _e("POSTGRES_DB", "seo_agent"))
    db_user: str = field(default_factory=lambda: _e("POSTGRES_USER", "seo_admin"))
    db_password: str = field(default_factory=lambda: _e("POSTGRES_PASSWORD"))
    cors_origins: list[str] = field(default_factory=lambda: [o.strip() for o in _e("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()])
    public_url: str = field(default_factory=lambda: _e("PUBLIC_URL").rstrip("/"))
    google_client_id: str = field(default_factory=lambda: _e("GOOGLE_CLIENT_ID"))
    google_client_secret: str = field(default_factory=lambda: _e("GOOGLE_CLIENT_SECRET"))
    free_runs_per_day: int = field(default_factory=lambda: int(_e("FREE_RUNS_PER_DAY", "2")))
    global_free_runs_per_day: int = field(default_factory=lambda: int(_e("GLOBAL_FREE_RUNS_PER_DAY", "40")))
    max_concurrent_runs: int = field(default_factory=lambda: int(_e("MAX_CONCURRENT_RUNS", "3")))
    llm_timeout: float = 90.0
    max_retries: int = 2

    @property
    def key_configured(self) -> bool:
        return self.gemini_api_key.lower() not in PLACEHOLDERS

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def conninfo(self) -> str:
        if self.database_url:  # hosted Postgres (Neon etc.)
            return self.database_url
        return make_conninfo(host=self.db_host, port=self.db_port, dbname=self.db_name,
                             user=self.db_user, password=self.db_password, connect_timeout=5)


settings = Settings()


def startup_report() -> None:
    if not settings.key_configured:
        log.warning("GEMINI_API_KEY is not set: only users with their own Gemini key can create blogs.")
    else:
        log.info("Shared Gemini key loaded (model=%s).", settings.llm_model)
    log.info("Google sign-in: %s", "on" if settings.google_enabled else "off (set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)")
