"""Keyword overlap skill matching — fallback when embeddings unavailable."""

def skill_match_score(candidate_skills: list[str], job_skills: list[str]) -> float:
    """
    Compute overlap ratio between candidate and job skill sets.
    Returns 0.0–1.0 (multiply by 100 for percentage).
    """
    if not job_skills:
        return 0.0

    cand = {s.lower().strip() for s in candidate_skills if s}
    job = {s.lower().strip() for s in job_skills if s}
    if not cand or not job:
        return 0.0

    overlap = len(cand & job)
    return overlap / len(job)
