from pydantic_settings import BaseSettings


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
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
