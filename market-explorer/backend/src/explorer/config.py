"""
Configuration for Market Explorer.

Loads settings from environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Database
    database_url: str = "postgresql://localhost/predict"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # CORS
    cors_origins: list[str] = ["http://localhost:3004"]

    class Config:
        env_prefix = "EXPLORER_"
        env_file = ".env"


settings = Settings()
