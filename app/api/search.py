import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.core.database import get_db
from app.core.security import get_current_user
from app.api.common import PageParams
from app.models.models import Job
from app.schemas.schemas import Paginated, JobOut

router = APIRouter(prefix="/search", tags=["Search"])
logger = logging.getLogger(__name__)


@router.get("/jobs", response_model=Paginated[JobOut])
async def search_jobs(
    query: str = Query(..., min_length=1),
    page: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    pattern = f"%{query.lower()}%"
    base = select(Job).where(
        or_(func.lower(Job.title).like(pattern), func.lower(Job.description).like(pattern))
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(
        base.order_by(Job.created_at.desc()).offset(page.offset).limit(page.limit)
    )).scalars().all()
    return Paginated(items=rows, total=total or 0, page=page.page, limit=page.limit)
