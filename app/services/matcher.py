import logging
from typing import Optional
import numpy as np

from app.core.config import settings
from app.ai.config.settings import get_ai_settings
from app.ai.matching_engine.job_matcher import calculate_match_score as blend_scores
from app.ai.matching_engine.skill_matcher import skill_match_score as keyword_skill_score

logger = logging.getLogger(__name__)

# PERF [CRITICAL]: model loaded ONCE at startup, not per request.
# sentence-transformers (and its torch dependency) is imported lazily so the
# app can boot without it when running against the AI microservice.
_model = None


def load_embedding_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info({"event": "embedding_model_loaded", "model": settings.EMBEDDING_MODEL})
    return _model


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def compute_match_score(
    candidate_skills: list[str],
    job_skills: list[str],
    candidate_text: str = "",
    job_description: str = "",
) -> dict:
    """
    Semantic similarity between candidate profile and job requirements.
    Returns: {match_score (0-100), matched_skills, missing_skills}
    """
    # EDGE CASE: both inputs empty — return before loading the (heavy) model
    if not candidate_skills and not candidate_text:
        logger.warning({"event": "match_empty_candidate"})
        return {"match_score": 0.0, "matched_skills": [], "missing_skills": list(job_skills)}

    if not job_skills and not job_description:
        logger.warning({"event": "match_empty_job"})
        return {"match_score": 0.0, "matched_skills": [], "missing_skills": []}

    model = load_embedding_model()

    # ── Skill-level semantic matching ────────────────────────────────────────
    matched: list[str] = []
    missing: list[str] = []
    skill_score = 0.0

    if candidate_skills and job_skills:
        # PERF [HIGH]: encode both lists in one batch call, not in a loop
        all_texts = candidate_skills + job_skills
        all_embeddings = model.encode(all_texts, convert_to_numpy=True, show_progress_bar=False)
        cand_embeddings = all_embeddings[: len(candidate_skills)]
        job_embeddings = all_embeddings[len(candidate_skills):]

        # REFACTOR: threshold pulled from AI config
        threshold = get_ai_settings().SKILL_MATCH_THRESHOLD

        for j_idx, j_skill in enumerate(job_skills):
            sims = [
                _cosine_similarity(cand_embeddings[c_idx], job_embeddings[j_idx])
                for c_idx in range(len(candidate_skills))
            ]
            if max(sims) >= threshold:
                matched.append(j_skill)
            else:
                missing.append(j_skill)

        skill_score = (len(matched) / len(job_skills)) * 100 if job_skills else 0.0

    # ── Document-level semantic matching ─────────────────────────────────────
    doc_score = 0.0
    if candidate_text and job_description:
        # PERF: single batch encode of 2 documents
        vecs = model.encode([candidate_text[:10_000], job_description[:10_000]],
                            convert_to_numpy=True, show_progress_bar=False)
        doc_score = _cosine_similarity(vecs[0], vecs[1]) * 100

    # ── Weighted blend via AI layer ───────────────────────────────────────────
    if candidate_skills and job_skills and candidate_text and job_description:
        final_score = blend_scores(skill_score, doc_score)
    elif candidate_skills and job_skills:
        final_score = round(skill_score, 2)
    elif candidate_text and job_description:
        final_score = round(doc_score, 2)
    else:
        # Fallback: keyword overlap when embeddings unavailable
        overlap = keyword_skill_score(candidate_skills, job_skills) * 100
        final_score = round(overlap, 2)

    final_score = min(final_score, 100.0)

    logger.info({
        "event": "match_computed",
        "skill_score": round(skill_score, 2),
        "doc_score": round(doc_score, 2),
        "final_score": final_score,
        "matched": len(matched),
        "missing": len(missing),
    })

    return {
        "match_score": final_score,
        "matched_skills": matched,
        "missing_skills": missing,
    }
