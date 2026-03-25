"""
config.py — Centralized settings loader for Job Application Automation.
All values are sourced from environment variables (via .env file).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (one level up from this file if needed)
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)


def _require(key: str) -> str:
    """Return env var value or raise a descriptive error."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"[config] Required environment variable '{key}' is missing or empty.\n"
            f"  → Copy .env.example to .env and fill in your values."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ── AI Provider ───────────────────────────────────────────────────────────────
AI_PROVIDER: str = _optional("AI_PROVIDER", "gemini").lower()  # "gemini" | "grok"

GEMINI_API_KEY: str = _optional("GEMINI_API_KEY")   
GEMINI_MODEL: str = _optional("GEMINI_MODEL", "gemini-2.0-flash")

GROK_API_KEY: str = _optional("GROK_API_KEY")
GROK_BASE_URL: str = _optional("GROK_BASE_URL", "https://api.x.ai/v1")
GROK_MODEL: str = _optional("GROK_MODEL", "grok-3")

# Validate the active provider's key
if AI_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise EnvironmentError(
        "[config] AI_PROVIDER=gemini but GEMINI_API_KEY is not set.\n"
        "  → Get a key at https://aistudio.google.com/apikey and add it to .env"
    )
if AI_PROVIDER == "grok" and not GROK_API_KEY:
    raise EnvironmentError(
        "[config] AI_PROVIDER=grok but GROK_API_KEY is not set.\n"
        "  → Add your xAI API key to .env"
    )

# ── SMTP ──────────────────────────────────────────────────────────────────────
SMTP_HOST: str = _optional("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = int(_optional("SMTP_PORT", "587"))
SMTP_USER: str = _require("SMTP_USER")
SMTP_PASSWORD: str = _require("SMTP_PASSWORD")

# ── Sender Profile ────────────────────────────────────────────────────────────
SENDER_NAME: str = _require("SENDER_NAME")
SENDER_PHONE: str = _optional("SENDER_PHONE")
SENDER_LINKEDIN: str = _optional("SENDER_LINKEDIN")
SENDER_EMAIL: str = _optional("SENDER_EMAIL") or SMTP_USER

# Profile summary text injected into AI prompt
PROFILE_SUMMARY: str = _require("PROFILE_SUMMARY")

# ── File Paths ────────────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).parent
JOBS_CSV_PATH: Path = BASE_DIR / _optional("JOBS_CSV_PATH", "jobs.csv")
CV_PATH: Path = BASE_DIR / _optional("CV_PATH", "cv.pdf")
SENT_LOG_PATH: Path = BASE_DIR / _optional("SENT_LOG_PATH", "sent_log.csv")
LOG_DIR: Path = BASE_DIR / _optional("LOG_DIR", "logs")

# ── Email Template ────────────────────────────────────────────────────────────
EMAIL_SUBJECT_TEMPLATE: str = _optional(
    "EMAIL_SUBJECT_TEMPLATE", "Application for {position} at {company}"
)

# ── Rate Limiting ─────────────────────────────────────────────────────────────
MIN_DELAY_SECONDS: float = float(_optional("MIN_DELAY_SECONDS", "20"))
MAX_DELAY_SECONDS: float = float(_optional("MAX_DELAY_SECONDS", "60"))

# ── Safety / Behaviour ────────────────────────────────────────────────────────
DRY_RUN: bool = _optional("DRY_RUN", "true").lower() in ("true", "1", "yes")
MAX_RETRIES: int = int(_optional("MAX_RETRIES", "2"))
