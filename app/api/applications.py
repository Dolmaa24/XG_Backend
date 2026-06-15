import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user, owner_or_staff, STAFF_ROLES
from app.models.models import Application, Job, Resume
from app.schemas.schemas import ApplicationCreate, ApplicationOut, MessageResponse, ErrorResponse
from app.services import ai_client
from app.services.ranker import compute_and_store_ranking

router = APIRouter(prefix="/applications", tags=["Applications (Candidate)"])
logger = logging.getLogger(__name__)


@router.get("/{user_id}", response_model=list[ApplicationOut])
async def list_applications(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    rows = (await db.execute(
        select(Application, Job).join(Job, Application.job_id == Job.id)
        .where(Application.user_id == user_id).order_by(Application.applied_at.desc())
    )).all()
    return [ApplicationOut(
        id=app.id, user_id=app.user_id, job_id=app.job_id, job_title=job.title,
        status=app.status.value, cover_note=app.cover_note, applied_at=app.applied_at,
    ) for app, job in rows]


@router.post("/apply", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED,
             responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def apply(
    payload: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in STAFF_ROLES and str(payload.user_id) != str(current_user.get("sub")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot apply on behalf of another user")

    job = await db.get(Job, payload.job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    existing = (await db.execute(
        select(Application).where(Application.user_id == payload.user_id, Application.job_id == payload.job_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already applied to this job")

    application = Application(user_id=payload.user_id, job_id=payload.job_id, cover_note=payload.cover_note)
    db.add(application)

    # Seed a ranking row using the candidate's latest parsed resume (best-effort).
    latest = (await db.execute(
        select(Resume).where(Resume.user_id == payload.user_id).order_by(Resume.uploaded_at.desc())
    )).scalars().first()
    if latest and latest.parse_status == "done" and isinstance(latest.parsed_data, dict):
        skills = latest.parsed_data.get("skills", []) or []
        cand_text = " ".join(skills + [e.get("raw", "") for e in latest.parsed_data.get("experience", [])])
        match = await ai_client.match(skills, job.required_skills, cand_text, job.description)
        try:
            await compute_and_store_ranking(
                db=db, user_id=payload.user_id, job_id=job.id,
                resume_score=latest.resume_score or 0.0,
                match_score=match["match_score"], interview_score=0.0,
            )
        except Exception as e:
            logger.warning({"event": "apply_ranking_seed_failed", "error": str(e)})

    await db.flush()
    await db.refresh(application)
    logger.info({"event": "application_created", "application_id": str(application.id)})
    return ApplicationOut(
        id=application.id, user_id=application.user_id, job_id=application.job_id,
        job_title=job.title, status=application.status.value,
        cover_note=application.cover_note, applied_at=application.applied_at,
    )


@router.delete("/{application_id}", response_model=MessageResponse, responses={404: {"model": ErrorResponse}})
async def withdraw_application(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    application = await db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    if current_user.get("role") not in STAFF_ROLES and str(application.user_id) != str(current_user.get("sub")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    await db.delete(application)
    return MessageResponse(message="Application withdrawn")
