from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    # Application
    APP_ENV: Literal["development", "production"] = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = Field(..., min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Database
    DATABASE_URL: str

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # File Storage
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    LOCAL_UPLOAD_DIR: str = "./uploads"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_REGION: str = "us-east-1"

    # AI / LLM
    LLM_PROVIDER: Literal["anthropic", "openai"] = "anthropic"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-20250514"

    # NLP Models
    SPACY_MODEL: str = "en_core_web_sm"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    SPACY_TEXT_CAP: int = 100_000          # max chars fed to spaCy to avoid OOM

    # Scoring Weights
    WEIGHT_RESUME: float = 0.30
    WEIGHT_MATCH: float = 0.30
    WEIGHT_INTERVIEW: float = 0.40

    # Interview settings
    MAX_INTERVIEW_QUESTIONS: int = 5       # was hardcoded in interviewer.py
    LLM_MAX_TOKENS: int = 1024             # was hardcoded in _call_anthropic/_call_openai
    ANSWER_MAX_LENGTH: int = 2000          # max candidate answer chars before truncation

    # Semantic matching thresholds
    SKILL_MATCH_THRESHOLD: float = 0.75   # cosine similarity threshold for skill match
    SKILL_SCORE_WEIGHT: float = 0.70       # blend weight: skill similarity vs doc similarity
    DOC_SCORE_WEIGHT: float = 0.30

    # Rate Limiting
    UPLOAD_RATE_LIMIT: str = "5/minute"
    LOGIN_RATE_LIMIT: str = "10/minute"

    # File Validation
    MAX_UPLOAD_SIZE_MB: int = 5
    ALLOWED_MIME_TYPES: str = "application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    @property
    def allowed_mime_types_list(self) -> list[str]:
        return [m.strip() for m in self.ALLOWED_MIME_TYPES.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    model_config = {"env_file": ".env", "case_sensitive": True}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
