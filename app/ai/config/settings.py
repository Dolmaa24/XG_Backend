"""
AI layer configuration — single source of truth via backend Settings.
Mirrors ai/config/settings.py from XTRAGRAD-AI commit e0bf2eb.
"""
from functools import lru_cache

from app.core.config import settings as app_settings


class AISettings:
    """Read-only AI configuration backed by pydantic Settings."""

    @property
    def LLM_PROVIDER(self) -> str:
        return app_settings.LLM_PROVIDER

    @property
    def LLM_MODEL(self) -> str:
        return app_settings.LLM_MODEL

    @property
    def MAX_INTERVIEW_QUESTIONS(self) -> int:
        return app_settings.MAX_INTERVIEW_QUESTIONS

    @property
    def LLM_MAX_TOKENS(self) -> int:
        return app_settings.LLM_MAX_TOKENS

    @property
    def SKILL_MATCH_THRESHOLD(self) -> float:
        return app_settings.SKILL_MATCH_THRESHOLD

    @property
    def SKILL_SCORE_WEIGHT(self) -> float:
        return app_settings.SKILL_SCORE_WEIGHT

    @property
    def DOC_SCORE_WEIGHT(self) -> float:
        return app_settings.DOC_SCORE_WEIGHT

    @property
    def SPACY_MODEL(self) -> str:
        return app_settings.SPACY_MODEL

    @property
    def EMBEDDING_MODEL(self) -> str:
        return app_settings.EMBEDDING_MODEL

    @property
    def ANSWER_MAX_LENGTH(self) -> int:
        return app_settings.ANSWER_MAX_LENGTH


@lru_cache()
def get_ai_settings() -> AISettings:
    return AISettings()
