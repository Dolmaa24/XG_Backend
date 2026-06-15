import logging
from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.core.security import staff_required
from app.api.common import PageParams
from app.schemas.schemas import Paginated, MatchResultOut
from app.services import aggregations
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Match Results (Admin)"])
logger = logging.getLogger(__name__)


@router.get("/match-results", response_model=Paginated[MatchResultOut])
async def match_results(
    page: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(staff_required),
):
    items, total = await aggregations.match_results(db, page.page, page.limit)
    return Paginated(items=items, total=total, page=page.page, limit=page.limit)
