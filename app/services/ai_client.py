"""
AI integration seam.

Every AI-powered feature in the backend goes through this module. When
`AI_SERVICE_ENABLED` is true we call the AI team's HTTP microservice; otherwise
(or if that service errors/times out) we fall back to the backend's own local
services (parser/matcher/interviewer) so the product always works.

The HTTP request/response shapes mirror docs/AI_INTEGRATION_CONTRACT.md.
"""
import logging
from typing import Optional

import anyio
import httpx

from app.core.config import settings
from app.services import matcher as local_matcher
from app.services import interviewer as local_interviewer

logger = logging.getLogger(__name__)


async def _call(path: str, payload: dict) -> Optional[dict]:
    """POST to the AI service. Returns parsed JSON, or None to signal fallback."""
    if not settings.AI_SERVICE_ENABLED:
        return None
    url = settings.AI_SERVICE_URL.rstrip("/") + path
    try:
        async with httpx.AsyncClient(timeout=settings.AI_SERVICE_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning({"event": "ai_service_call_failed", "path": path, "error": str(e)})
        return None


# ── Matching ───────────────────────────────────────────────────────────────

async def match(candidate_skills: list[str], job_skills: list[str],
                candidate_text: str = "", job_description: str = "") -> dict:
    remote = await _call("/match", {
        "candidate_skills": candidate_skills, "job_skills": job_skills,
        "candidate_text": candidate_text, "job_description": job_description,
    })
    if remote and "match_score" in remote:
        return remote
    # Local fallback (blocking embedding call -> threadpool)
    return await anyio.to_thread.run_sync(
        lambda: local_matcher.compute_match_score(
            candidate_skills, job_skills, candidate_text, job_description)
    )


# ── Skill analysis ────────────────────────────────────────────────────────────

async def skill_analysis(skills: list[str], target_skills: list[str]) -> dict:
    remote = await _call("/skill-analysis", {"skills": skills, "target_skills": target_skills})
    if remote and "strengths" in remote:
        return remote
    skills_set = {s.lower() for s in skills}
    target_set = [t for t in target_skills] or skills
    strengths = sorted([t for t in target_set if t.lower() in skills_set]) or sorted(skills)
    gaps = sorted([t for t in target_set if t.lower() not in skills_set])
    return {
        "strengths": strengths,
        "gaps": gaps,
        "skill_levels": {s: "intermediate" for s in skills},
        "recommendations": [f"Strengthen your knowledge of {g}" for g in gaps[:5]],
    }


# ── Recommendations ────────────────────────────────────────────────────────

async def recommend_jobs(candidate_skills: list[str], jobs: list[dict]) -> list[dict]:
    """jobs: [{job_id,title,required_skills,description}] -> ranked recommendations."""
    remote = await _call("/recommendations/jobs", {"candidate_skills": candidate_skills, "jobs": jobs})
    if remote and "recommendations" in remote:
        return remote["recommendations"]

    recs = []
    for job in jobs:
        res = await match(candidate_skills, job.get("required_skills", []),
                          " ".join(candidate_skills), job.get("description", ""))
        recs.append({
            "job_id": job.get("job_id"),
            "title": job.get("title"),
            "score": res["match_score"],
            "matched_skills": res.get("matched_skills", []),
            "missing_skills": res.get("missing_skills", []),
            "reasons": [f"Matches {len(res.get('matched_skills', []))} required skill(s)"],
        })
    recs.sort(key=lambda r: r["score"], reverse=True)
    return recs


async def recommend_candidates(job: dict, candidates: list[dict]) -> list[dict]:
    remote = await _call("/recommendations/candidates", {"job": job, "candidates": candidates})
    if remote and "recommendations" in remote:
        return remote["recommendations"]
    ranked = sorted(candidates, key=lambda c: c.get("final_score", 0.0), reverse=True)
    return [{
        "user_id": c.get("user_id"),
        "name": c.get("name"),
        "final_score": c.get("final_score", 0.0),
        "summary": c.get("summary"),
    } for c in ranked]


# ── Interview turns (used by mock interview + real interview) ─────────────────

_FALLBACK_CATEGORIES = ["technical", "behavioural", "situational"]


def _template_question(skills: list[str], n: int) -> str:
    if skills:
        skill = skills[n % len(skills)]
        return f"Describe a project where you applied {skill} and the impact it had."
    return "Tell me about a challenging problem you solved and how you approached it."


async def interview_first_question(job_title: str, required_skills: list[str],
                                   candidate_profile: dict) -> dict:
    remote = await _call("/interview/turn", {
        "job_title": job_title, "required_skills": required_skills,
        "candidate_profile": candidate_profile, "conversation": [], "latest_answer": None,
    })
    if remote and remote.get("question"):
        return {"question": remote["question"], "category": remote.get("category", "general")}
    try:
        return await anyio.to_thread.run_sync(
            lambda: local_interviewer.generate_first_question(job_title, required_skills, candidate_profile))
    except Exception as e:
        logger.warning({"event": "interview_first_fallback_template", "error": str(e)})
        return {"question": _template_question(required_skills, 0), "category": "technical"}


async def interview_evaluate(job_title: str, required_skills: list[str], candidate_profile: dict,
                             conversation: list[dict], latest_answer: str,
                             question_index: int = 0) -> dict:
    remote = await _call("/interview/turn", {
        "job_title": job_title, "required_skills": required_skills,
        "candidate_profile": candidate_profile, "conversation": conversation,
        "latest_answer": latest_answer,
    })
    if remote and remote.get("type") == "evaluation":
        return {
            "answer_score": float(remote.get("score", 5)) * 10 if remote.get("score", 0) <= 10 else float(remote.get("score")),
            "feedback": remote.get("feedback", "Recorded."),
            "next_question": remote.get("next_question"),
            "interview_complete": bool(remote.get("complete", remote.get("next_question") is None)),
        }
    try:
        return await anyio.to_thread.run_sync(
            lambda: local_interviewer.evaluate_answer_and_next(
                job_title, required_skills, candidate_profile, conversation, latest_answer))
    except Exception as e:
        logger.warning({"event": "interview_eval_fallback_template", "error": str(e)})
        # Heuristic fallback scoring based on answer length/content
        words = len((latest_answer or "").split())
        score = max(20.0, min(90.0, words * 4.0))
        complete = (question_index + 1) >= settings.MAX_INTERVIEW_QUESTIONS
        return {
            "answer_score": round(score, 2),
            "feedback": "Answer recorded. Add specific examples and outcomes to strengthen it.",
            "next_question": None if complete else _template_question(required_skills, question_index + 1),
            "interview_complete": complete,
        }
