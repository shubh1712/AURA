from typing import List, Optional
from pydantic import field_validator, model_validator
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
    AURA_FRAMER_OPERATION_TIMEOUT_SECONDS: Optional[float] = None
    AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS: Optional[float] = None

    @field_validator("ANALYSIS_TIMEOUT_SECONDS")
    @classmethod
    def validate_analysis_timeout(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("ANALYSIS_TIMEOUT_SECONDS must be strictly greater than 0.0")
        return v

    @field_validator("AURA_FRAMER_OPERATION_TIMEOUT_SECONDS")
    @classmethod
    def validate_framer_timeout(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0.0:
            raise ValueError("AURA_FRAMER_OPERATION_TIMEOUT_SECONDS must be strictly greater than 0.0")
        return v

    @field_validator("AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS")
    @classmethod
    def validate_boardroom_timeout(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0.0:
            raise ValueError("AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS must be strictly greater than 0.0")
        return v

    # Action Intelligence configuration
    AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS: float = 120.0
    AURA_ACTION_INTELLIGENCE_HTTP_TIMEOUT_SECONDS: float = 90.0
    AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS: float = 180.0
    AURA_ACTION_INTELLIGENCE_MAX_RETRIES: int = 0

    @field_validator("AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS")
    @classmethod
    def validate_action_intelligence_op_timeout(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS must be strictly greater than 0.0")
        return v

    @field_validator("AURA_ACTION_INTELLIGENCE_HTTP_TIMEOUT_SECONDS")
    @classmethod
    def validate_action_intelligence_http_timeout(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("AURA_ACTION_INTELLIGENCE_HTTP_TIMEOUT_SECONDS must be strictly greater than 0.0")
        return v

    @field_validator("AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS")
    @classmethod
    def validate_action_intelligence_claim_ttl(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS must be strictly greater than 0.0")
        return v

    @field_validator("AURA_ACTION_INTELLIGENCE_MAX_RETRIES")
    @classmethod
    def validate_action_intelligence_max_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError("AURA_ACTION_INTELLIGENCE_MAX_RETRIES must be non-negative")
        return v

    @model_validator(mode="after")
    def validate_action_intelligence_timeout_chain(self) -> "Settings":
        if self.AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS < self.AURA_ACTION_INTELLIGENCE_HTTP_TIMEOUT_SECONDS:
            raise ValueError(
                "AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS must be greater than or equal to "
                "AURA_ACTION_INTELLIGENCE_HTTP_TIMEOUT_SECONDS"
            )
        if self.AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS <= self.AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS:
            raise ValueError(
                "AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS must be strictly greater than "
                "AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS to prevent premature claim expiration"
            )
        return self

    # Asynchronous job configuration
    AURA_JOBS_DB_PATH: str = "aura_jobs.db"
    AURA_MAX_JOB_WORKERS: int = 4
    AURA_JOB_DEFAULT_TIMEOUT_SECONDS: float = 180.0

    @field_validator("AURA_MAX_JOB_WORKERS")
    @classmethod
    def validate_max_job_workers(cls, v: int) -> int:
        if v < 1:
            raise ValueError("AURA_MAX_JOB_WORKERS must be at least 1")
        return v

    @field_validator("AURA_JOB_DEFAULT_TIMEOUT_SECONDS")
    @classmethod
    def validate_job_default_timeout(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("AURA_JOB_DEFAULT_TIMEOUT_SECONDS must be strictly greater than 0.0")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
