"""
In-process resume parsing job, run via FastAPI BackgroundTasks.

This keeps the core upload->parse flow self-contained (no running Celery worker
required) while still using the backend's local parser. The Celery task in
app/tasks/celery_tasks.py remains available for deployments that prefer a queue.
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.models import Resume
from app.services.parser import parse_resume

logger = logging.getLogger(__name__)


async def parse_and_store(resume_id: str, file_path: str) -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with SessionLocal() as session:
            resume = await session.get(Resume, UUID(str(resume_id)))
            if not resume:
                logger.error({"event": "parse_job_resume_not_found", "resume_id": resume_id})
                return
            try:
                parsed = parse_resume(file_path)
                resume.resume_score = parsed.pop("resume_score", 0.0)
                resume.parsed_data = parsed
                resume.parse_status = "done"
                resume.parsed_at = datetime.now(timezone.utc)
            except Exception as e:
                resume.parse_status = "failed"
                logger.error({"event": "parse_job_failed", "resume_id": resume_id, "error": str(e)})
            await session.commit()
            logger.info({"event": "parse_job_complete", "resume_id": resume_id,
                         "status": resume.parse_status})
    finally:
        await engine.dispose()
