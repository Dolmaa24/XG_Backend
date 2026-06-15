import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Resume, Job, Ranking
from app.schemas.schemas import MatchRequest, MatchResponse, ErrorResponse
from app.services.matcher import compute_match_score
from app.services.ranker import compute_and_store_ranking
from sqlalchemy import select

router = APIRouter(prefix="/match", tags=["Matching"])
logger = logging.getLogger(__name__)


@router.post(
    "/score",
    response_model=MatchResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def match_candidate(
    payload: MatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    resume = await db.get(Resume, payload.resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")

    if resume.parse_status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume parsing is still in progress. Try again shortly.",
        )
    if resume.parse_status == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume parsing failed. Please re-upload the file.",
        )

    job = await db.get(Job, payload.job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    parsed = resume.parsed_data or {}
    candidate_skills = parsed.get("skills", [])
    candidate_text = " ".join([
        " ".join(candidate_skills),
        " ".join(e.get("raw", "") for e in parsed.get("experience", [])),
        " ".join(e.get("raw", "") for e in parsed.get("education", [])),
    ])

    result = compute_match_score(
        candidate_skills=candidate_skills,
        job_skills=job.required_skills,
        candidate_text=candidate_text,
        job_description=job.description,
    )

    # Persist match score into rankings table
    await compute_and_store_ranking(
        db=db,
        user_id=resume.user_id,
        job_id=job.id,
        resume_score=resume.resume_score or 0.0,
        match_score=result["match_score"],
        interview_score=0.0,
    )

    logger.info({
        "event": "match_scored",
        "resume_id": str(payload.resume_id),
        "job_id": str(payload.job_id),
        "match_score": result["match_score"],
    })

    return MatchResponse(
        resume_id=payload.resume_id,
        job_id=payload.job_id,
        match_score=result["match_score"],
        matched_skills=result["matched_skills"],
        missing_skills=result["missing_skills"],
    )
