import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.core.database import get_db
from app.core.security import staff_required
from app.api.common import PageParams
from app.models.models import User, Resume, Application, UserRole
from app.schemas.schemas import (
    Paginated, CandidateSummary, CandidateDetail, MessageResponse, ErrorResponse,
)

router = APIRouter(prefix="/candidates", tags=["Candidates (Admin)"])
logger = logging.getLogger(__name__)


async def _summary(db: AsyncSession, user: User) -> CandidateSummary:
    resume_count = await db.scalar(
        select(func.count()).select_from(Resume).where(Resume.user_id == user.id))
    app_count = await db.scalar(
        select(func.count()).select_from(Application).where(Application.user_id == user.id))
    return CandidateSummary(
        id=user.id, name=user.name, email=user.email, role=user.role.value,
        created_at=user.created_at, resume_count=resume_count or 0,
        application_count=app_count or 0,
    )


@router.get("", response_model=Paginated[CandidateSummary])
async def list_candidates(
    page: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    base = select(User).where(User.role == UserRole.candidate)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(
        base.order_by(User.created_at.desc()).offset(page.offset).limit(page.limit)
    )).scalars().all()
    items = [await _summary(db, u) for u in rows]
    return Paginated(items=items, total=total or 0, page=page.page, limit=page.limit)


@router.get("/search", response_model=Paginated[CandidateSummary])
async def search_candidates(
    q: str = Query(..., min_length=1),
    page: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    pattern = f"%{q.lower()}%"
    base = select(User).where(
        User.role == UserRole.candidate,
        or_(func.lower(User.name).like(pattern), func.lower(User.email).like(pattern)),
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(
        base.order_by(User.created_at.desc()).offset(page.offset).limit(page.limit)
    )).scalars().all()
    items = [await _summary(db, u) for u in rows]
    return Paginated(items=items, total=total or 0, page=page.page, limit=page.limit)


@router.get("/{candidate_id}", response_model=CandidateDetail,
            responses={404: {"model": ErrorResponse}})
async def get_candidate(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    user = await db.get(User, candidate_id)
    if not user or user.role != UserRole.candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    summary = await _summary(db, user)
    latest = (await db.execute(
        select(Resume).where(Resume.user_id == user.id).order_by(Resume.uploaded_at.desc())
    )).scalars().first()
    skills = []
    if latest and isinstance(latest.parsed_data, dict):
        skills = latest.parsed_data.get("skills", []) or []

    return CandidateDetail(
        **summary.model_dump(),
        skills=skills,
        latest_resume_id=latest.id if latest else None,
        latest_resume_score=latest.resume_score if latest else None,
    )


@router.delete("/{candidate_id}", response_model=MessageResponse,
               responses={404: {"model": ErrorResponse}})
async def delete_candidate(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    user = await db.get(User, candidate_id)
    if not user or user.role != UserRole.candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    await db.delete(user)  # cascades resumes/interviews/rankings/applications/profile/settings
    logger.info({"event": "candidate_deleted", "candidate_id": str(candidate_id)})
    return MessageResponse(message="Candidate deleted")
