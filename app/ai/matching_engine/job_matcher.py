"""Weighted blend of skill-level and document-level match scores."""

from app.ai.config.settings import get_ai_settings


def calculate_match_score(skill_score: float, document_score: float) -> float:
    """
    Blend skill and document scores using configured weights.
    Inputs and output are on 0–100 scale.
    """
    cfg = get_ai_settings()
    blended = (
        skill_score * cfg.SKILL_SCORE_WEIGHT
        + document_score * cfg.DOC_SCORE_WEIGHT
    )
    return round(min(blended, 100.0), 2)
