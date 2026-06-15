import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "ai_hr_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10, name="tasks.parse_resume")
def parse_resume_task(self, resume_id: str, file_path: str):
    """
    Background task: parse resume PDF and update DB record.
    Retries up to 3 times on failure.
    """
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.models.models import Resume
    from app.services.parser import parse_resume

    logger.info({"event": "task_started", "task": "parse_resume", "resume_id": resume_id})

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

        async with SessionLocal() as session:
            resume = await session.get(Resume, UUID(resume_id))
            if not resume:
                logger.error({"event": "task_resume_not_found", "resume_id": resume_id})
                return

            try:
                parsed = parse_resume(file_path)
                resume.parsed_data = parsed
                resume.resume_score = parsed.pop("resume_score", 0.0)
                resume.parse_status = "done"
                resume.parsed_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info({
                    "event": "task_parse_success",
                    "resume_id": resume_id,
                    "resume_score": resume.resume_score,
                })
            except Exception as e:
                resume.parse_status = "failed"
                await session.commit()
                logger.error({"event": "task_parse_failed", "resume_id": resume_id, "error": str(e)})
                raise self.retry(exc=e)

        await engine.dispose()

    asyncio.run(_run())
