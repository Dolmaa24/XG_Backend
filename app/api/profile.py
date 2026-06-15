import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user, owner_or_staff, STAFF_ROLES
from app.models.models import Profile, User
from app.schemas.schemas import (
    ProfileCreate, ProfileUpdate, ProfileOut, AvatarUploadResponse, ErrorResponse,
)
from app.utils.file_handler import validate_image_upload, save_file

router = APIRouter(prefix="/profile", tags=["Profile (Candidate)"])
logger = logging.getLogger(__name__)


def _is_owner_or_staff(current_user: dict, user_id: uuid.UUID) -> bool:
    return current_user.get("role") in STAFF_ROLES or str(user_id) == str(current_user.get("sub"))


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED,
             responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def create_profile(
    payload: ProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not _is_owner_or_staff(current_user, payload.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create another user's profile")
    if not await db.get(User, payload.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    existing = (await db.execute(select(Profile).where(Profile.user_id == payload.user_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile already exists; use PUT to update")

    data = payload.model_dump()
    profile = Profile(**data)
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return profile


@router.get("/{user_id}", response_model=ProfileOut, responses={404: {"model": ErrorResponse}})
async def get_profile(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    profile = (await db.execute(select(Profile).where(Profile.user_id == user_id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.put("/{user_id}", response_model=ProfileOut, responses={404: {"model": ErrorResponse}})
async def update_profile(
    user_id: uuid.UUID,
    payload: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(owner_or_staff("user_id")),
):
    profile = (await db.execute(select(Profile).where(Profile.user_id == user_id))).scalar_one_or_none()
    if not profile:
        # Upsert: create if missing so PUT is idempotent for first-time setup
        if not await db.get(User, user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        profile = Profile(user_id=user_id)
        db.add(profile)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.flush()
    await db.refresh(profile)
    return profile


@router.post("/upload-avatar", response_model=AvatarUploadResponse,
             responses={403: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}})
async def upload_avatar(
    user_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not _is_owner_or_staff(current_user, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot change another user's avatar")
    content = await validate_image_upload(file)
    path = await save_file(content, file.filename or "avatar.png", f"avatars/{user_id}")

    profile = (await db.execute(select(Profile).where(Profile.user_id == user_id))).scalar_one_or_none()
    if not profile:
        profile = Profile(user_id=user_id)
        db.add(profile)
    profile.avatar_url = path
    await db.flush()
    return AvatarUploadResponse(user_id=user_id, avatar_url=path)
