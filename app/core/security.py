import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as aioredis
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

# SECURITY [HIGH]: pre-computed dummy hash used during login when user is not found.
# Ensures constant-time bcrypt verification to prevent user-enumeration via timing attack.
DUMMY_HASH = pwd_context.hash("dummy-timing-prevention-string-not-real")

# Roles that may access the Admin Dashboard surface.
STAFF_ROLES = {"admin", "hr"}

# Redis key prefix for revoked-token (logout) blocklist.
_BLOCKLIST_PREFIX = "jwt:blocklist:"

# Lazily-initialised async Redis client shared across requests.
_redis: Optional[aioredis.Redis] = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        # SECURITY: unique token id so individual tokens can be revoked on logout
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    logger.info({"event": "token_created", "subject": subject, "role": role})
    return token


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        # SECURITY [MEDIUM]: explicit expiry check — python-jose validates exp but
        # being explicit guards against library bugs
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError as e:
        logger.warning({"event": "token_invalid", "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Token revocation (logout) ────────────────────────────────────────────────

async def revoke_token(payload: dict) -> None:
    """
    Add a token's jti to the Redis blocklist until its natural expiry.
    Called on logout. Fails open (logs) if Redis is unavailable.
    """
    jti = payload.get("jti")
    if not jti:
        return
    exp = payload.get("exp")
    now = int(datetime.now(timezone.utc).timestamp())
    ttl = max(1, int(exp) - now) if exp else settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    try:
        await _get_redis().set(f"{_BLOCKLIST_PREFIX}{jti}", "1", ex=ttl)
        logger.info({"event": "token_revoked", "jti": jti})
    except Exception as e:
        logger.error({"event": "token_revoke_failed", "error": str(e)})


async def is_token_revoked(jti: Optional[str]) -> bool:
    if not jti:
        return False
    try:
        return await _get_redis().exists(f"{_BLOCKLIST_PREFIX}{jti}") == 1
    except Exception as e:
        # SECURITY: fail open so a Redis outage doesn't lock everyone out,
        # but log loudly so the gap is visible.
        logger.error({"event": "blocklist_check_failed", "error": str(e)})
        return False


# ── Dependencies ──────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    payload = decode_access_token(credentials.credentials)
    if await is_token_revoked(payload.get("jti")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def require_role(required_role: str):
    async def _checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return _checker


async def staff_required(current_user: dict = Depends(get_current_user)) -> dict:
    """Admin Dashboard guard — allows admin or hr roles."""
    if current_user.get("role") not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff access required",
        )
    return current_user


def owner_or_staff(user_id_param: str = "user_id"):
    """
    Dependency factory: allow the request only if the authenticated user owns
    the targeted resource (path param `user_id_param`) OR is staff.
    """
    from fastapi import Request

    async def _checker(request: Request, current_user: dict = Depends(get_current_user)) -> dict:
        target = request.path_params.get(user_id_param)
        if current_user.get("role") in STAFF_ROLES:
            return current_user
        if target is not None and str(target) == str(current_user.get("sub")):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own resources",
        )
    return _checker


hr_required = require_role("hr")
candidate_required = require_role("candidate")
