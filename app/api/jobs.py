import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.core.database import get_db
from app.core.security import staff_required, get_current_user, owner_or_staff
from app.api.common import PageParams
from app.models.models import Job, Resume
from app.schemas.schemas import (
    Paginated, JobCreate, JobUpdate, JobOut, JobRecommendation, MessageResponse, ErrorResponse,
)
from app.services import ai_client

router = APIRouter(prefix="/jobs", tags=["Jobs"])
logger = logging.getLogger(__name__)


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED,
             responses={403: {"model": ErrorResponse}})
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(staff_required),
):
    job = Job(
        title=payload.title, description=payload.description,
        required_skills=payload.required_skills, experience_years=payload.experience_years,
        weight_resume=payload.weight_resume, weight_match=payload.weight_match,
        weight_interview=payload.weight_interview, created_by=uuid.UUID(current_user["sub"]),
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    logger.info({"event": "job_created", "job_id": str(job.id)})
    return job


@router.get("", response_model=Paginated[JobOut])
async def list_jobs(
    page: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    total = await db.scalar(select(func.count()).select_from(Job))
    rows = (await db.execute(
        select(Job).order_by(Job.created_at.desc()).offset(page.offset).limit(page.limit)
    )).scalars().all()
    return Paginated(items=rows, total=total or 0, page=page.page, limit=page.limit)


@router.get("/search", response_model=Paginated[JobOut])
async def search_jobs(
    query: str = Query(..., min_length=1),
    page: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    pattern = f"%{query.lower()}%"
    base = select(Job).where(
        or_(func.lower(Job.title).like(pattern), func.lower(Job.description).like(pattern))
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(
        base.order_by(Job.created_at.desc()).offset(page.offset).limit(page.limit)
    )).scalars().all()
    return Paginated(items=rows, total=total or 0, page=page.page, limit=page.limit)


@router.get("/recommendations/{user_id}", response_model=list[JobRecommendation])
async def job_recommendations(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    latest = (await db.execute(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc())
    )).scalars().first()
    candidate_skills = []
    if latest and isinstance(latest.parsed_data, dict):
        candidate_skills = latest.parsed_data.get("skills", []) or []

    jobs = (await db.execute(select(Job))).scalars().all()
    job_dicts = [{"job_id": str(j.id), "title": j.title,
                  "required_skills": j.required_skills, "description": j.description} for j in jobs]
    recs = await ai_client.recommend_jobs(candidate_skills, job_dicts)
    return [JobRecommendation(
        job_id=uuid.UUID(r["job_id"]), title=r.get("title", ""), score=r.get("score", 0.0),
        matched_skills=r.get("matched_skills", []), missing_skills=r.get("missing_skills", []),
        reasons=r.get("reasons", []),
    ) for r in recs if r.get("job_id")]


@router.put("/{job_id}", response_model=JobOut, responses={404: {"model": ErrorResponse}})
async def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(job, field, value)
    await db.flush()
    await db.refresh(job)
    logger.info({"event": "job_updated", "job_id": str(job_id)})
    return job


@router.delete("/{job_id}", response_model=MessageResponse, responses={404: {"model": ErrorResponse}})
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    await db.delete(job)
    logger.info({"event": "job_deleted", "job_id": str(job_id)})
    return MessageResponse(message="Job deleted")
