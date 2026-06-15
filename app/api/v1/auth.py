import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, DUMMY_HASH
from app.core.config import settings
from app.models.models import User
from app.schemas.schemas import RegisterRequest, LoginRequest, TokenResponse, UserOut, ErrorResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
# SECURITY [HIGH]: rate limit registration to prevent account creation abuse
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info({"event": "user_registered", "user_id": str(user.id), "role": str(user.role)})
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}},
)
# SECURITY [CRITICAL]: rate limit login to prevent brute-force attacks
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # SECURITY [HIGH]: always run verify_password even when user not found
    # to prevent timing-based user enumeration attacks
    password_to_check = user.password_hash if user else DUMMY_HASH
    password_valid = verify_password(payload.password, password_to_check)

    if not user or not password_valid:
        logger.warning({"event": "login_failed", "email": payload.email})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token(subject=str(user.id), role=user.role.value)
    logger.info({"event": "login_success", "user_id": str(user.id)})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
