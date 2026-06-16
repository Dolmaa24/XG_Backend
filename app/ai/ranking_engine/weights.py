"""Default ranking weights — used when job-level weights are not set."""

from app.core.config import settings

RESUME_WEIGHT = settings.WEIGHT_RESUME
MATCH_WEIGHT = settings.WEIGHT_MATCH
INTERVIEW_WEIGHT = settings.WEIGHT_INTERVIEW

DEFAULT_WEIGHTS = {
    "resume": RESUME_WEIGHT,
    "match": MATCH_WEIGHT,
    "interview": INTERVIEW_WEIGHT,
}


def compute_weighted_score(
    resume_score: float,
    match_score: float,
    interview_score: float,
    weights: dict[str, float] | None = None,
) -> float:
    """Compute final score using provided or default weights."""
    w = weights or DEFAULT_WEIGHTS
    return round(
        resume_score * w["resume"]
        + match_score * w["match"]
        + interview_score * w["interview"],
        2,
    )
