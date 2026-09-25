"""Runtime configuration. Reads env; never requires a .env to boot."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Config:
    ROOT = ROOT
    SECRET_KEY = os.environ.get("SECRET_KEY") or "workdey-dev-only-change-me"
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8080").rstrip("/")
    PORT = _int("PORT", 8080)
    TIMEZONE = os.environ.get("TIMEZONE", "Africa/Lagos")

    _db = os.environ.get("DATABASE_URL", "sqlite:///instance/workdey.db")
    if _db.startswith("sqlite:///") and not _db.startswith("sqlite:////"):
        rel = _db.replace("sqlite:///", "", 1)
        db_path = (ROOT / rel).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(db_path)
    else:
        SQLALCHEMY_DATABASE_URI = _db
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN", "").strip()
    LINKEDIN_COOKIE = os.environ.get("LINKEDIN_COOKIE", "").strip()

    SOURCE_FLAGS = {
        "x": _bool("SOURCE_X_ENABLED", True),
        "linkedin": _bool("SOURCE_LINKEDIN_JOBS_ENABLED", True),
        "linkedin_posts": _bool("SOURCE_LINKEDIN_POSTS_ENABLED", True),
        "instagram": _bool("SOURCE_INSTAGRAM_ENABLED", True),
        "workdey": _bool("SOURCE_WORKDEY_ENABLED", True),
    }

    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()
    BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "alerts@workdey.app")
    BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "WorkDey")
    BREVO_TEMPLATE_ID = os.environ.get("BREVO_TEMPLATE_ID", "").strip() or None

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    GROQ_BASE = "https://api.groq.com/openai/v1"

    DEMO_MODE = _bool("DEMO_MODE", True)
    DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "blessing@workdey.app")
    DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "WorkDey2026!")

    INGEST_EVERY_MINUTES = _int("INGEST_EVERY_MINUTES", 15)
    MATCH_TICK_SECONDS = _int("MATCH_TICK_SECONDS", 30)
    PING_EVERY_SECONDS = _int("PING_EVERY_SECONDS", 20)
    KEEPALIVE_URL = os.environ.get("KEEPALIVE_URL", "").strip()
    EMAIL_DAILY_CAP = _int("EMAIL_DAILY_CAP", 3)
    APIFY_MAX_ITEMS = _int("APIFY_MAX_ITEMS", 30)
    LLM_DAILY_CAP = _int("LLM_DAILY_CAP", 20)

    UPLOAD_DIR = ROOT / "instance" / "uploads"
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024

    ACTORS = {
        "workdey_career": "em07_adoz/workdey-career-agent-task",
    }
