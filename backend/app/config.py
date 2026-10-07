from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AURA Decision-Intelligence Platform"
    VERSION: str = "0.0.1-pre-alpha"
    API_V1_STR: str = "/api"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True

    # CORS configuration for Next.js frontend communication
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # LLM / Gemini configuration (Google Cloud Vertex AI)
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_CLOUD_LOCATION: str = "global"

    # Search / Brave configuration
    BRAVE_SEARCH_API_KEY: Optional[str] = None

    # Analysis execution configuration
    ANALYSIS_TIMEOUT_SECONDS: float = 120.0

    @field_validator("ANALYSIS_TIMEOUT_SECONDS")
    @classmethod
    def validate_analysis_timeout(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("ANALYSIS_TIMEOUT_SECONDS must be strictly greater than 0.0")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
