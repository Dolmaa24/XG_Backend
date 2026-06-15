import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import staff_required, owner_or_staff
from app.models.models import User, Job, Resume, Ranking, Application
from app.schemas.schemas import SkillAnalysisResponse, CandidateRecommendation, ErrorResponse
from app.services import ai_client

router = APIRouter(prefix="/ai", tags=["AI"])
logger = logging.getLogger(__name__)


@router.get("/recommendations", response_model=list[CandidateRecommendation])
async def ai_recommendations(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    """Top candidates across all jobs (admin AI recommendations)."""
    rows = (await db.execute(
        select(Ranking, User).join(User, Ranking.user_id == User.id)
        .order_by(Ranking.final_score.desc()).limit(limit)
    )).all()
    candidates = [{
        "user_id": str(user.id), "name": user.name,
        "final_score": ranking.final_score, "summary": ranking.summary,
    } for ranking, user in rows]

    recs = await ai_client.recommend_candidates(job={}, candidates=candidates)
    return [CandidateRecommendation(
        user_id=uuid.UUID(str(r["user_id"])), name=r.get("name", ""),
        final_score=r.get("final_score", 0.0), summary=r.get("summary"),
    ) for r in recs if r.get("user_id")]


@router.get("/skill-analysis/{user_id}", response_model=SkillAnalysisResponse,
            responses={404: {"model": ErrorResponse}})
async def skill_analysis(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    latest = (await db.execute(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc())
    )).scalars().first()
    skills = []
    if latest and isinstance(latest.parsed_data, dict):
        skills = latest.parsed_data.get("skills", []) or []

    # Target skills: required skills of jobs the candidate applied to (else all jobs)
    applied = (await db.execute(
        select(Job).join(Application, Application.job_id == Job.id)
        .where(Application.user_id == user_id)
    )).scalars().all()
    if not applied:
        applied = (await db.execute(select(Job).limit(20))).scalars().all()
    target_skills = sorted({s for j in applied for s in (j.required_skills or [])})

    result = await ai_client.skill_analysis(skills, target_skills)
    return SkillAnalysisResponse(user_id=user_id, **result)
