import logging
import uuid
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request, status,
)
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import staff_required
from app.core.config import settings
from app.api.common import PageParams
from app.models.models import Resume
from app.schemas.schemas import (
    Paginated, ResumeProfileOut, ResumeUploadResponse, MessageResponse, ErrorResponse,
)
from app.utils.file_handler import validate_upload, save_file, read_file, delete_file
from app.services.resume_jobs import parse_and_store

router = APIRouter(prefix="/resumes", tags=["Resumes (Admin)"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post("/upload", response_model=ResumeUploadResponse,
             status_code=status.HTTP_202_ACCEPTED,
             responses={413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}})
@limiter.limit(settings.UPLOAD_RATE_LIMIT)
async def upload_resume(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: uuid.UUID = Form(...),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    content = await validate_upload(file)
    file_path = await save_file(content, file.filename or "resume.pdf", str(user_id))
    resume = Resume(user_id=user_id, file_path=file_path,
                    original_filename=file.filename or "resume.pdf", parse_status="pending")
    db.add(resume)
    await db.flush()
    await db.refresh(resume)
    background.add_task(parse_and_store, str(resume.id), file_path)
    logger.info({"event": "resume_uploaded_admin", "resume_id": str(resume.id)})
    return ResumeUploadResponse(resume_id=resume.id, parse_status="pending",
                                message="Resume uploaded. Parsing in progress.")


@router.get("", response_model=Paginated[ResumeProfileOut])
async def list_resumes(
    page: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    total = await db.scalar(select(func.count()).select_from(Resume))
    rows = (await db.execute(
        select(Resume).order_by(Resume.uploaded_at.desc()).offset(page.offset).limit(page.limit)
    )).scalars().all()
    return Paginated(items=rows, total=total or 0, page=page.page, limit=page.limit)


@router.get("/{resume_id}", response_model=ResumeProfileOut,
            responses={404: {"model": ErrorResponse}})
async def get_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return resume


@router.get("/download/{resume_id}", responses={404: {"model": ErrorResponse}})
async def download_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    try:
        data = read_file(resume.file_path)
    except Exception as e:
        logger.error({"event": "resume_download_failed", "resume_id": str(resume_id), "error": str(e)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume file not available")
    return Response(
        content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{resume.original_filename}"'},
    )


@router.delete("/{resume_id}", response_model=MessageResponse,
               responses={404: {"model": ErrorResponse}})
async def delete_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    delete_file(resume.file_path)
    await db.delete(resume)
    logger.info({"event": "resume_deleted_admin", "resume_id": str(resume_id)})
    return MessageResponse(message="Resume deleted")
