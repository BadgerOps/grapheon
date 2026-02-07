from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


def _load_version() -> str:
    version_path = Path(__file__).resolve().parent / "VERSION"
    try:
        return version_path.read_text().strip()
    except FileNotFoundError:
        return "0.1.0"


class Settings(BaseSettings):
    """Application configuration using Pydantic settings."""

    # Database
    DATABASE_URL: str = "sqlite:///./data/network.db"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # Application
    APP_NAME: str = "Graphēon"
    APP_VERSION: str = _load_version()
    DEBUG: bool = False

    # ── Authentication & Authorization ─────────────────────────────────
    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # Auth feature flags
    AUTH_ENABLED: bool = True  # Master switch — False = all endpoints public
    ENFORCE_AUTH: bool = False  # Gradual rollout — False = auth optional

    # Local admin bootstrap (set via env vars for first-run setup)
    LOCAL_ADMIN_USERNAME: Optional[str] = None
    LOCAL_ADMIN_EMAIL: Optional[str] = None
    LOCAL_ADMIN_PASSWORD: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
