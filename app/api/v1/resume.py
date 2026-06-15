import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models.models import Resume
from app.schemas.schemas import ResumeUploadResponse, ResumeProfileOut, ErrorResponse
from app.utils.file_handler import validate_upload, save_file
from app.tasks.celery_tasks import parse_resume_task

router = APIRouter(prefix="/resume", tags=["Resume"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}},
)
@limiter.limit(settings.UPLOAD_RATE_LIMIT)
async def upload_resume(
    request,  # required by slowapi
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["sub"]

    # Validate size and MIME type
    content = await validate_upload(file)

    # Save to storage
    file_path = await save_file(content, file.filename or "resume.pdf", user_id)

    # Create DB record with pending status
    resume = Resume(
        user_id=UUID(user_id),
        file_path=file_path,
        original_filename=file.filename or "resume.pdf",
        parse_status="pending",
    )
    db.add(resume)
    await db.flush()
    await db.refresh(resume)

    # Dispatch background parse task
    parse_resume_task.delay(str(resume.id), file_path)

    logger.info({"event": "resume_uploaded", "resume_id": str(resume.id), "user_id": user_id})

    return ResumeUploadResponse(
        resume_id=resume.id,
        parse_status="pending",
        message="Resume uploaded successfully. Parsing in progress.",
    )


@router.get(
    "/profile/{resume_id}",
    response_model=ResumeProfileOut,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def get_resume_profile(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")

    # Only the owner or HR can view
    if str(resume.user_id) != current_user["sub"] and current_user.get("role") != "hr":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return resume
