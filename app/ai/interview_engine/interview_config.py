"""Interview session configuration."""

from app.ai.config.settings import get_ai_settings

MAX_QUESTIONS = get_ai_settings().MAX_INTERVIEW_QUESTIONS

QUESTION_TYPES = [
    "technical",
    "behavioral",
    "situational",
]
