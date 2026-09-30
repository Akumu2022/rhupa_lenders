import os
from pathlib import Path


class Settings:
    """Minimal env-backed settings. No pydantic-settings dependency needed at this scale."""

    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")

    # Migrations need the table OWNER (DDL rights); the running app should
    # connect as a restricted role that row-level security applies to (the
    # owner, neondb_owner on Neon, bypasses it). When set, Alembic uses this
    # URL and the app uses DATABASE_URL. Unset: both use DATABASE_URL.
    migration_database_url: str = os.environ.get("MIGRATION_DATABASE_URL", "") or database_url

    # The business day every "today" decision uses — due dates, overdue
    # status, daily penalties, "due today" dashboards. Servers run in UTC;
    # Kenya is UTC+3, so using the server's date would put anything between
    # 00:00 and 03:00 EAT on the wrong day. Platform-wide for now (every
    # tenant is in the Kenyan market, CLAUDE.md §1).
    business_timezone: str = os.environ.get("BUSINESS_TIMEZONE", "Africa/Nairobi")

    # Shared secret for scheduled jobs calling /internal/* (the daily
    # end-of-day run). Unset = those endpoints are disabled (404).
    cron_secret: str = os.environ.get("CRON_SECRET", "")

    # CLAUDE.md §2: access tokens are short-lived, no refresh-token flow in the MVP.
    jwt_secret_key: str = os.environ.get("JWT_SECRET_KEY", "dev-only-insecure-secret-change-me")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "45"))

    # CLAUDE.md §9, §16: KYC documents live outside the web root and are never
    # served from a static/guessable path — only via an authenticated,
    # tenant-scoped, role-gated endpoint (added in M3).
    kyc_storage_root: Path = Path(os.environ.get("KYC_STORAGE_ROOT", "./storage/kyc")).resolve()

    # The React dev server and the API run on different ports/origins; the
    # browser enforces CORS even though curl/pytest never exercise it.
    cors_allowed_origins: list[str] = os.environ.get(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")


settings = Settings()
