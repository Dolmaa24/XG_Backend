import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import staff_required
from app.schemas.schemas import CountItem, DistributionBucket
from app.services import aggregations

router = APIRouter(prefix="/analytics", tags=["Analytics (Admin)"])
logger = logging.getLogger(__name__)


@router.get("/skills", response_model=list[CountItem])
async def analytics_skills(db: AsyncSession = Depends(get_db), _: dict = Depends(staff_required)):
    return [CountItem(**c) for c in await aggregations.analytics_skills(db)]


@router.get("/status", response_model=list[CountItem])
async def analytics_status(db: AsyncSession = Depends(get_db), _: dict = Depends(staff_required)):
    return [CountItem(**c) for c in await aggregations.analytics_status(db)]


@router.get("/match-scores", response_model=list[DistributionBucket])
async def analytics_match_scores(db: AsyncSession = Depends(get_db), _: dict = Depends(staff_required)):
    return [DistributionBucket(**b) for b in await aggregations.analytics_match_scores(db)]


@router.get("/interview-performance")
async def analytics_interview_performance(db: AsyncSession = Depends(get_db), _: dict = Depends(staff_required)):
    return await aggregations.analytics_interview_performance(db)
