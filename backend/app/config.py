from typing import Any, List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AURA Decision-Intelligence Platform"
    VERSION: str = "0.0.1-pre-alpha"
    API_V1_STR: str = "/api"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # CORS configuration for Next.js frontend communication
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    import json
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return v

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

    # Storage backend configuration
    AURA_STORAGE_BACKEND: str = "sqlite"

    @field_validator("AURA_STORAGE_BACKEND")
    @classmethod
    def validate_storage_backend(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in ("sqlite", "firestore"):
            raise ValueError(
                f"Unsupported AURA_STORAGE_BACKEND '{v}'. Supported backends are: 'sqlite', 'firestore'."
            )
        return cleaned

    FIRESTORE_DATABASE: str = "(default)"

    # Execution mode configuration
    AURA_EXECUTION_MODE: str = "local"

    @field_validator("AURA_EXECUTION_MODE")
    @classmethod
    def validate_execution_mode(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in ("local", "cloud_tasks"):
            raise ValueError(
                f"Unsupported AURA_EXECUTION_MODE '{v}'. Supported modes are: 'local', 'cloud_tasks'."
            )
        return cleaned

    # Cloud Tasks configuration
    AURA_CLOUD_TASKS_PROJECT: Optional[str] = None
    AURA_CLOUD_TASKS_LOCATION: str = "asia-southeast1"
    AURA_CLOUD_TASKS_QUEUE: str = "aura-analysis-jobs"
    AURA_CLOUD_TASKS_WORKER_URL: Optional[str] = None
    AURA_CLOUD_TASKS_SERVICE_ACCOUNT: Optional[str] = None
    AURA_OIDC_AUDIENCE: Optional[str] = None
    AURA_JOB_LEASE_SECONDS: float = 300.0
    AURA_CLOUD_TASKS_DISPATCH_DEADLINE_SECONDS: int = 600

    @field_validator("AURA_JOB_LEASE_SECONDS")
    @classmethod
    def validate_lease_seconds(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("AURA_JOB_LEASE_SECONDS must be strictly greater than 0.0")
        return v

    @field_validator("AURA_CLOUD_TASKS_DISPATCH_DEADLINE_SECONDS")
    @classmethod
    def validate_dispatch_deadline_seconds(cls, v: int) -> int:
        if v < 15 or v > 1800:
            raise ValueError(
                "AURA_CLOUD_TASKS_DISPATCH_DEADLINE_SECONDS must be between 15 and 1800 seconds (Cloud Tasks HTTP limits)."
            )
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
