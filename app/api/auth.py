import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password, create_access_token, DUMMY_HASH,
    get_current_user, staff_required, revoke_token,
)
from app.core.config import settings
from app.models.models import User
from app.schemas.schemas import (
    RegisterRequest, LoginRequest, LoginResponse, UserOut, MessageResponse, ErrorResponse,
)

router = APIRouter(tags=["Authentication"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             responses={409: {"model": ErrorResponse}})
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="An account with this email already exists")
    user = User(name=payload.name, email=payload.email,
                password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    logger.info({"event": "user_registered", "user_id": str(user.id), "role": str(user.role)})
    return user


@router.post("/auth/login", response_model=LoginResponse, responses={401: {"model": ErrorResponse}})
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # SECURITY [HIGH]: constant-time verify to prevent user enumeration
    password_to_check = user.password_hash if user else DUMMY_HASH
    password_valid = verify_password(payload.password, password_to_check)

    if not user or not password_valid:
        logger.warning({"event": "login_failed", "email": payload.email})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect email or password")

    token = create_access_token(subject=str(user.id), role=user.role.value)
    logger.info({"event": "login_success", "user_id": str(user.id)})
    return LoginResponse(
        access_token=token, token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, user=user,
    )


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(current_user: dict = Depends(get_current_user)):
    await revoke_token(current_user)
    return MessageResponse(message="Logged out successfully")


@router.get("/admin/profile", response_model=UserOut, responses={403: {"model": ErrorResponse}})
async def admin_profile(current_user: dict = Depends(staff_required), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, uuid.UUID(current_user["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
