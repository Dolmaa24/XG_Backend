import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user, owner_or_staff, STAFF_ROLES
from app.models.models import Assessment, Resume
from app.schemas.schemas import (
    AssessmentStartResponse, AssessmentQuestion, AssessmentSubmitRequest,
    AssessmentResultResponse, ErrorResponse,
)
from app.services import assessment as assessment_svc

router = APIRouter(prefix="/assessment", tags=["Skill Assessment (Candidate)"])
logger = logging.getLogger(__name__)


@router.get("/start", response_model=AssessmentStartResponse)
async def start_assessment(
    skills: str = Query("", description="Comma-separated skills; defaults to your resume skills"),
    count: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = uuid.UUID(current_user["sub"])
    skill_list = [s.strip() for s in skills.split(",") if s.strip()]
    if not skill_list:
        latest = (await db.execute(
            select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc())
        )).scalars().first()
        if latest and isinstance(latest.parsed_data, dict):
            skill_list = latest.parsed_data.get("skills", []) or []

    questions = await assessment_svc.generate(skill_list, count)  # includes answer_index
    record = Assessment(user_id=user_id, skills=skill_list, questions=questions,
                        answers={}, status="in_progress")
    db.add(record)
    await db.flush()
    await db.refresh(record)

    public = [AssessmentQuestion(id=q["id"], skill=q["skill"], type=q["type"],
                                 prompt=q["prompt"], options=q["options"]) for q in questions]
    return AssessmentStartResponse(assessment_id=record.id, questions=public)


@router.post("/submit", response_model=AssessmentResultResponse,
             responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}})
async def submit_assessment(
    payload: AssessmentSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    record = await db.get(Assessment, payload.assessment_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    if current_user.get("role") not in STAFF_ROLES and str(record.user_id) != str(current_user.get("sub")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if record.status == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assessment already submitted")

    pct, correct, total = assessment_svc.score(record.questions, payload.answers)
    record.answers = payload.answers
    record.score = pct
    record.status = "completed"
    record.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return AssessmentResultResponse(
        assessment_id=record.id, user_id=record.user_id, score=pct, status=record.status,
        correct=correct, total=total, completed_at=record.completed_at,
    )


@router.get("/result/{user_id}", response_model=AssessmentResultResponse,
            responses={404: {"model": ErrorResponse}})
async def assessment_result(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    record = (await db.execute(
        select(Assessment).where(Assessment.user_id == user_id, Assessment.status == "completed")
        .order_by(Assessment.completed_at.desc())
    )).scalars().first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No completed assessment found")
    total = len(record.questions or [])
    correct = round((record.score or 0) / 100 * total) if total else 0
    return AssessmentResultResponse(
        assessment_id=record.id, user_id=record.user_id, score=record.score,
        status=record.status, correct=correct, total=total, completed_at=record.completed_at,
    )
