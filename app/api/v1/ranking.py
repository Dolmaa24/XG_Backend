import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hr_required
from app.schemas.schemas import RankingResponse, ErrorResponse
from app.services.ranker import get_ranked_candidates

router = APIRouter(prefix="/ranking", tags=["Ranking"])
logger = logging.getLogger(__name__)


@router.get(
    "/{job_id}",
    response_model=RankingResponse,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def get_rankings(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(hr_required),
):
    try:
        result = await get_ranked_candidates(db=db, job_id=job_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    logger.info({
        "event": "ranking_viewed",
        "job_id": str(job_id),
        "hr_user": current_user["sub"],
        "candidates": result["total_candidates"],
    })

    return result
