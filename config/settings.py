"""
config/settings.py
Environment-driven settings for the AI Job Hunter agent (v3).
All settings are read from environment variables (loaded from .env via python-dotenv).

v3 changes:
  - Dropped Telegram & WhatsApp settings
  - Renamed email vars to SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL_TO
  - Default run interval changed to 6 hours

v5 changes:
  - Added semantic classifier thresholds

Usage:
    from config.settings import settings
    print(settings.smtp_user)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level up from config/)
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=False)  # don't override actual env vars


class Settings:
    """Central settings object. Reads all config from environment variables."""

    # ── Database ───────────────────────────────────────────────────────────────
    @property
    def db_path(self) -> Path:
        val = os.environ.get("DB_PATH", "")
        return Path(val) if val else _ROOT / "database" / "jobs.db"

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    @property
    def smtp_host(self) -> str:
        return os.environ.get("SMTP_HOST", os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com"))

    @property
    def smtp_port(self) -> int:
        return int(os.environ.get("SMTP_PORT", os.environ.get("EMAIL_SMTP_PORT", "587")))

    @property
    def smtp_user(self) -> str:
        return os.environ.get("SMTP_USER", os.environ.get("EMAIL_USERNAME", ""))

    @property
    def smtp_pass(self) -> str:
        return os.environ.get("SMTP_PASS", os.environ.get("EMAIL_PASSWORD", ""))

    @property
    def smtp_from(self) -> str:
        """From address defaults to SMTP_USER if not set."""
        return os.environ.get("SMTP_FROM", self.smtp_user)

    @property
    def alert_email_to(self) -> list[str]:
        raw = os.environ.get("ALERT_EMAIL_TO", os.environ.get("EMAIL_TO", ""))
        return [addr.strip() for addr in raw.split(",") if addr.strip()]

    # ── Gemini / LLM ──────────────────────────────────────────────────────────
    @property
    def google_api_key(self) -> str:
        return os.environ.get("GOOGLE_API_KEY", "")

    @property
    def llm_model(self) -> str:
        return os.environ.get("LLM_MODEL", "gemini-2.0-flash")

    # ── Scheduler ─────────────────────────────────────────────────────────────
    @property
    def run_interval_hours(self) -> int:
        """How often the pipeline runs (in hours). Default: 8 (v9)."""
        return int(os.environ.get("RUN_INTERVAL_HOURS", "8"))

    # ── Pipeline ──────────────────────────────────────────────────────────────
    @property
    def companies_config(self) -> Path:
        return _ROOT / "config" / "companies.json"

    @property
    def semantic_upper_threshold(self) -> float:
        """Score above this -> auto-accept job role relevance."""
        return float(os.environ.get("SEMANTIC_UPPER_THRESHOLD", "0.35"))

    @property
    def semantic_lower_threshold(self) -> float:
        """Score below this -> auto-reject job role relevance."""
        return float(os.environ.get("SEMANTIC_LOWER_THRESHOLD", "-0.15"))

    @property
    def request_delay(self) -> float:
        """Seconds to wait between HTTP requests (be polite)."""
        return float(os.environ.get("REQUEST_DELAY", "1.0"))

    @property
    def notify_enabled(self) -> bool:
        """Set NOTIFY_ENABLED=false to disable all notifications (dry-run mode)."""
        return os.environ.get("NOTIFY_ENABLED", "true").lower() not in ("false", "0", "no")

    @property
    def dry_run(self) -> bool:
        """Set DRY_RUN=true to run the pipeline without saving to DB or notifying."""
        return os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes")

    @property
    def log_level(self) -> str:
        return os.environ.get("LOG_LEVEL", "INFO").upper()


settings = Settings()
