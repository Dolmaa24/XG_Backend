import logging
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import staff_required, owner_or_staff
from app.api.common import PageParams
from app.models.models import MockInterview, User
from app.schemas.schemas import Paginated, InterviewResultOut

router = APIRouter(tags=["Interviews"])
logger = logging.getLogger(__name__)


def _to_out(itv: MockInterview, user_name: str | None = None) -> InterviewResultOut:
    return InterviewResultOut(
        id=itv.id, user_id=itv.user_id, job_id=None, candidate_name=user_name,
        job_title=itv.role, interview_score=itv.score, status=itv.status,
        started_at=itv.started_at, completed_at=itv.completed_at,
    )


@router.get("/interviews", response_model=Paginated[InterviewResultOut])
async def list_interviews(
    page: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    total = await db.scalar(select(func.count()).select_from(MockInterview))
    rows = (await db.execute(
        select(MockInterview, User).join(User, MockInterview.user_id == User.id)
        .order_by(MockInterview.started_at.desc()).offset(page.offset).limit(page.limit)
    )).all()
    items = [_to_out(itv, user.name) for itv, user in rows]
    return Paginated(items=items, total=total or 0, page=page.page, limit=page.limit)


@router.get("/interviews/status/{user_id}", response_model=list[InterviewResultOut])
async def interview_status(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    rows = (await db.execute(
        select(MockInterview).where(MockInterview.user_id == user_id)
        .order_by(MockInterview.started_at.desc())
    )).scalars().all()
    return [_to_out(itv) for itv in rows]
