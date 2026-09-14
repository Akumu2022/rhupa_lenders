import os
from pathlib import Path


class Settings:
    """Minimal env-backed settings. No pydantic-settings dependency needed at this scale."""

    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")

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
