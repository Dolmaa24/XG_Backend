import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import owner_or_staff
from app.models.models import Settings as SettingsModel, User
from app.schemas.schemas import SettingsUpdate, SettingsOut, ErrorResponse

router = APIRouter(prefix="/settings", tags=["Settings (Candidate)"])
logger = logging.getLogger(__name__)

_DEFAULT_PREFS = {"notifications": True, "theme": "light", "profile_visibility": "public"}


@router.get("/{user_id}", response_model=SettingsOut, responses={404: {"model": ErrorResponse}})
async def get_settings(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    row = (await db.execute(select(SettingsModel).where(SettingsModel.user_id == user_id))).scalar_one_or_none()
    if not row:
        # Lazily create defaults the first time settings are read.
        if not await db.get(User, user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        row = SettingsModel(user_id=user_id, preferences=dict(_DEFAULT_PREFS))
        db.add(row)
        await db.flush()
        await db.refresh(row)
    return row


@router.put("/{user_id}", response_model=SettingsOut, responses={404: {"model": ErrorResponse}})
async def update_settings(
    user_id: uuid.UUID,
    payload: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    row = (await db.execute(select(SettingsModel).where(SettingsModel.user_id == user_id))).scalar_one_or_none()
    if not row:
        if not await db.get(User, user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        row = SettingsModel(user_id=user_id, preferences=dict(_DEFAULT_PREFS))
        db.add(row)
    # Merge so partial updates don't drop existing keys.
    merged = {**(row.preferences or {}), **payload.preferences}
    row.preferences = merged
    await db.flush()
    await db.refresh(row)
    return row
