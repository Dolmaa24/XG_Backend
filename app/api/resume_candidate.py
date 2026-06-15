import logging
import uuid
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Request, status,
)
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user, owner_or_staff, STAFF_ROLES
from app.core.config import settings
from app.models.models import Resume
from app.schemas.schemas import ResumeUploadResponse, ResumeProfileOut, MessageResponse, ErrorResponse
from app.utils.file_handler import validate_upload, save_file, delete_file
from app.services.resume_jobs import parse_and_store

router = APIRouter(prefix="/resume", tags=["Resume (Candidate)"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


def _owns(current_user: dict, owner_id: uuid.UUID) -> bool:
    return current_user.get("role") in STAFF_ROLES or str(owner_id) == str(current_user.get("sub"))


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_202_ACCEPTED,
             responses={413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}})
@limiter.limit(settings.UPLOAD_RATE_LIMIT)
async def upload_resume(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = uuid.UUID(current_user["sub"])
    content = await validate_upload(file)
    file_path = await save_file(content, file.filename or "resume.pdf", str(user_id))
    resume = Resume(user_id=user_id, file_path=file_path,
                    original_filename=file.filename or "resume.pdf", parse_status="pending")
    db.add(resume)
    await db.flush()
    await db.refresh(resume)
    background.add_task(parse_and_store, str(resume.id), file_path)
    logger.info({"event": "resume_uploaded", "resume_id": str(resume.id), "user_id": str(user_id)})
    return ResumeUploadResponse(resume_id=resume.id, parse_status="pending",
                                message="Resume uploaded. Parsing in progress.")


@router.get("/{user_id}", response_model=list[ResumeProfileOut])
async def get_user_resumes(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    rows = (await db.execute(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc())
    )).scalars().all()
    return rows


@router.delete("/{resume_id}", response_model=MessageResponse, responses={404: {"model": ErrorResponse}})
async def delete_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    if not _owns(current_user, resume.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    delete_file(resume.file_path)
    await db.delete(resume)
    return MessageResponse(message="Resume deleted")


@router.put("/{resume_id}", response_model=ResumeUploadResponse, responses={404: {"model": ErrorResponse}})
async def replace_resume(
    resume_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    if not _owns(current_user, resume.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    content = await validate_upload(file)
    delete_file(resume.file_path)
    new_path = await save_file(content, file.filename or "resume.pdf", str(resume.user_id))
    resume.file_path = new_path
    resume.original_filename = file.filename or "resume.pdf"
    resume.parse_status = "pending"
    resume.parsed_data = None
    resume.resume_score = None
    await db.flush()
    background.add_task(parse_and_store, str(resume.id), new_path)
    return ResumeUploadResponse(resume_id=resume.id, parse_status="pending",
                                message="Resume replaced. Re-parsing in progress.")
