import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user, hr_required
from app.models.models import Job
from app.schemas.schemas import JobCreate, JobOut, ErrorResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])
logger = logging.getLogger(__name__)


@router.post(
    "/create",
    response_model=JobOut,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"model": ErrorResponse}},
)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(hr_required),
):
    job = Job(
        title=payload.title,
        description=payload.description,
        required_skills=payload.required_skills,
        experience_years=payload.experience_years,
        weight_resume=payload.weight_resume,
        weight_match=payload.weight_match,
        weight_interview=payload.weight_interview,
        created_by=UUID(current_user["sub"]),
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    logger.info({"event": "job_created", "job_id": str(job.id), "title": job.title})
    return job


@router.get("/", response_model=list[JobOut])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    result = await db.execute(select(Job).order_by(Job.created_at.desc()))
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobOut, responses={404: {"model": ErrorResponse}})
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
