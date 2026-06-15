import logging
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Interview, Resume, Job, Ranking
from app.schemas.schemas import (
    InterviewStartRequest, InterviewStartResponse,
    InterviewRespondRequest, InterviewRespondResponse, ErrorResponse,
)
from app.services.interviewer import (
    generate_first_question, evaluate_answer_and_next, compute_final_interview_score
)
from app.services.ranker import compute_and_store_ranking

router = APIRouter(prefix="/interview", tags=["Interview"])
logger = logging.getLogger(__name__)


@router.post(
    "/start",
    response_model=InterviewStartResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def start_interview(
    payload: InterviewStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    resume = await db.get(Resume, payload.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if resume.parse_status != "done":
        raise HTTPException(status_code=400, detail="Resume must be fully parsed before starting an interview")

    job = await db.get(Job, payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Prevent duplicate active interviews
    existing = await db.execute(
        select(Interview).where(
            Interview.user_id == resume.user_id,
            Interview.job_id == job.id,
            Interview.status == "active",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An active interview session already exists for this job")

    parsed = resume.parsed_data or {}
    first = generate_first_question(
        job_title=job.title,
        required_skills=job.required_skills,
        candidate_profile=parsed,
    )

    interview = Interview(
        user_id=resume.user_id,
        job_id=job.id,
        conversation=[{"question": first["question"], "category": first["category"], "answer": None, "answer_score": None}],
        status="active",
    )
    db.add(interview)
    await db.flush()
    await db.refresh(interview)

    logger.info({"event": "interview_started", "interview_id": str(interview.id)})

    return InterviewStartResponse(
        interview_id=interview.id,
        first_question=first["question"],
        job_title=job.title,
    )


@router.post(
    "/respond",
    response_model=InterviewRespondResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def respond_to_interview(
    payload: InterviewRespondRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    interview = await db.get(Interview, payload.interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if interview.status == "completed":
        raise HTTPException(status_code=400, detail="This interview session has already been completed")

    if not payload.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")

    # Load related job and resume for context
    job = await db.get(Job, interview.job_id)
    resume_result = await db.execute(
        select(Resume).where(Resume.user_id == interview.user_id).order_by(Resume.uploaded_at.desc())
    )
    resume = resume_result.scalars().first()
    parsed = resume.parsed_data if resume else {}

    # Record answer on last unanswered turn
    conversation = list(interview.conversation)
    last_turn = conversation[-1]
    last_turn["answer"] = payload.answer

    result = evaluate_answer_and_next(
        job_title=job.title,
        required_skills=job.required_skills,
        candidate_profile=parsed or {},
        conversation=conversation[:-1],
        latest_answer=payload.answer,
    )

    last_turn["answer_score"] = result["answer_score"]
    last_turn["feedback"] = result["feedback"]

    # Append next question turn if interview not complete
    if not result["interview_complete"] and result["next_question"]:
        conversation.append({
            "question": result["next_question"],
            "category": "general",
            "answer": None,
            "answer_score": None,
        })

    interview.conversation = conversation

    final_interview_score = None
    if result["interview_complete"]:
        interview.status = "completed"
        interview.completed_at = datetime.now(timezone.utc)
        final_interview_score = compute_final_interview_score(conversation)
        interview.interview_score = final_interview_score

        # Update ranking with final interview score
        ranking_result = await db.execute(
            select(Ranking).where(
                Ranking.user_id == interview.user_id,
                Ranking.job_id == interview.job_id,
            )
        )
        ranking = ranking_result.scalar_one_or_none()
        resume_score = resume.resume_score if resume else 0.0
        match_score = ranking.match_score if ranking else 0.0

        await compute_and_store_ranking(
            db=db,
            user_id=interview.user_id,
            job_id=interview.job_id,
            resume_score=resume_score,
            match_score=match_score,
            interview_score=final_interview_score,
        )

    await db.flush()

    logger.info({
        "event": "answer_submitted",
        "interview_id": str(interview.id),
        "complete": result["interview_complete"],
        "answer_score": result["answer_score"],
    })

    return InterviewRespondResponse(
        next_question=result["next_question"],
        answer_score=result["answer_score"],
        feedback=result["feedback"],
        interview_complete=result["interview_complete"],
        final_interview_score=final_interview_score,
    )
