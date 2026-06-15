import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, STAFF_ROLES
from app.core.config import settings
from app.models.models import MockInterview
from app.schemas.schemas import (
    MockInterviewStartRequest, MockInterviewStartResponse,
    MockInterviewSubmitRequest, MockInterviewSubmitResponse, MockQuestionsResponse, ErrorResponse,
)
from app.services import ai_client

router = APIRouter(prefix="/mock-interview", tags=["Mock Interview (Candidate)"])
logger = logging.getLogger(__name__)


@router.post("/start", response_model=MockInterviewStartResponse, status_code=status.HTTP_201_CREATED)
async def start_mock_interview(
    payload: MockInterviewStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = uuid.UUID(current_user["sub"])
    first = await ai_client.interview_first_question(
        job_title=payload.role or "General Interview",
        required_skills=payload.skills,
        candidate_profile={"skills": payload.skills},
    )
    mock = MockInterview(
        user_id=user_id, role=payload.role, skills=payload.skills,
        conversation=[{"question": first["question"], "category": first.get("category", "general"),
                       "answer": None, "answer_score": None}],
        status="active",
    )
    db.add(mock)
    await db.flush()
    await db.refresh(mock)
    return MockInterviewStartResponse(mock_interview_id=mock.id, first_question=first["question"])


@router.post("/submit", response_model=MockInterviewSubmitResponse,
             responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}})
async def submit_mock_answer(
    payload: MockInterviewSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    mock = await db.get(MockInterview, payload.mock_interview_id)
    if not mock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mock interview not found")
    if current_user.get("role") not in STAFF_ROLES and str(mock.user_id) != str(current_user.get("sub")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if mock.status == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This mock interview is already complete")

    conversation = list(mock.conversation)
    answered = sum(1 for t in conversation if t.get("answer"))
    last_turn = conversation[-1]
    last_turn["answer"] = payload.answer

    result = await ai_client.interview_evaluate(
        job_title=mock.role or "General Interview", required_skills=mock.skills or [],
        candidate_profile={"skills": mock.skills or []}, conversation=conversation[:-1],
        latest_answer=payload.answer, question_index=answered,
    )
    last_turn["answer_score"] = result["answer_score"]
    last_turn["feedback"] = result["feedback"]

    if not result["interview_complete"] and result.get("next_question"):
        conversation.append({"question": result["next_question"], "category": "general",
                             "answer": None, "answer_score": None})

    mock.conversation = conversation
    final_score = None
    if result["interview_complete"]:
        mock.status = "completed"
        mock.completed_at = datetime.now(timezone.utc)
        scores = [t["answer_score"] for t in conversation if t.get("answer_score") is not None]
        final_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        mock.score = final_score

    await db.flush()
    return MockInterviewSubmitResponse(
        next_question=result.get("next_question"), answer_score=result["answer_score"],
        feedback=result["feedback"], complete=result["interview_complete"], final_score=final_score,
    )


@router.get("/questions", response_model=MockQuestionsResponse)
async def mock_questions(
    skills: str = Query("", description="Comma-separated skills"),
    role: str = Query("", description="Target role"),
    count: int = Query(5, ge=1, le=15),
    _: dict = Depends(get_current_user),
):
    """Preview a set of practice questions for the given skills/role (no session created)."""
    skill_list = [s.strip() for s in skills.split(",") if s.strip()]
    questions: list[str] = []
    first = await ai_client.interview_first_question(
        job_title=role or "General Interview", required_skills=skill_list,
        candidate_profile={"skills": skill_list})
    questions.append(first["question"])
    # Generate follow-ups via the evaluate fallback path (no real answer needed for previews)
    for i in range(1, count):
        skill = skill_list[i % len(skill_list)] if skill_list else None
        if skill:
            questions.append(f"What challenges have you faced working with {skill}, and how did you handle them?")
        else:
            questions.append("Tell me about a time you had to learn something new quickly.")
    return MockQuestionsResponse(questions=questions[:count])
