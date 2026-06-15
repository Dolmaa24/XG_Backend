import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import staff_required
from app.schemas.schemas import DashboardSummary, ActivityItem, ProgressStage
from app.services import aggregations

router = APIRouter(prefix="/dashboard", tags=["Dashboard (Admin)"])
logger = logging.getLogger(__name__)


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(db: AsyncSession = Depends(get_db), _: dict = Depends(staff_required)):
    return DashboardSummary(**await aggregations.summary(db))


@router.get("/activity", response_model=list[ActivityItem])
async def dashboard_activity(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    return [ActivityItem(**a) for a in await aggregations.activity(db, limit)]


@router.get("/progress", response_model=list[ProgressStage])
async def dashboard_progress(db: AsyncSession = Depends(get_db), _: dict = Depends(staff_required)):
    return [ProgressStage(**p) for p in await aggregations.progress(db)]
