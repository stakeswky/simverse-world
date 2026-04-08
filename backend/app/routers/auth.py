import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.user import RegisterRequest, LoginRequest, AuthResponse, UserResponse
from app.services.auth_service import register_user, login_user, create_token
from app.services.linuxdo_auth import LinuxDoOAuth, find_or_create_user

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OAuth state storage — Redis-first with in-memory fallback
# ---------------------------------------------------------------------------
# Redis key pattern: oauth_state:{state}  TTL: 600 s
# Falls back to an in-memory dict when Redis is unavailable (e.g. local dev
# without Redis running).

_STATE_TTL = 600  # seconds
_REDIS_KEY_PREFIX = "oauth_state:"

# In-memory fallback: state -> expiry timestamp
_mem_states: dict[str, float] = {}

# Lazy Redis client — initialised once on first use
_redis_client = None


def _get_redis():
    """Return a redis.Redis client, or None if Redis is unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis as _redis_lib  # type: ignore
        client = _redis_lib.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        _redis_client = client
        logger.info("OAuth state storage: Redis connected (%s)", settings.redis_url)
        return _redis_client
    except Exception as exc:
        logger.warning("OAuth state storage: Redis unavailable (%s) — using in-memory fallback", exc)
        return None


def _store_state(state: str) -> None:
    """Persist *state* with a 600-second TTL."""
    r = _get_redis()
    if r is not None:
        try:
            r.set(f"{_REDIS_KEY_PREFIX}{state}", "1", ex=_STATE_TTL)
            return
        except Exception as exc:
            logger.warning("Redis set failed: %s — falling back to memory", exc)

    # Memory fallback
    _mem_states[state] = time.time() + _STATE_TTL
    # Prune expired entries
    now = time.time()
    expired = [k for k, exp in list(_mem_states.items()) if exp <= now]
    for k in expired:
        _mem_states.pop(k, None)


def _validate_and_delete_state(state: str) -> bool:
    """Return True and remove *state* if valid; return False if missing/expired."""
    r = _get_redis()
    if r is not None:
        try:
            key = f"{_REDIS_KEY_PREFIX}{state}"
            # Atomic check-and-delete via pipeline
            pipe = r.pipeline()
            pipe.exists(key)
            pipe.delete(key)
            exists, _ = pipe.execute()
            return bool(exists)
        except Exception as exc:
            logger.warning("Redis pipeline failed: %s — falling back to memory", exc)

    # Memory fallback
    exp = _mem_states.pop(state, None)
    if exp is None:
        return False
    return time.time() < exp


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user, token = await register_user(db, req.name, req.email, req.password)
    return AuthResponse(access_token=token, user=UserResponse(
        id=user.id, name=user.name, email=user.email,
        avatar=user.avatar, soul_coin_balance=user.soul_coin_balance
    ))

@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await login_user(db, req.email, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user, token = result
    return AuthResponse(access_token=token, user=UserResponse(
        id=user.id, name=user.name, email=user.email,
        avatar=user.avatar, soul_coin_balance=user.soul_coin_balance
    ))


@router.get("/linuxdo/login")
async def linuxdo_login():
    """Redirect to LinuxDo OAuth2 authorize page."""
    if not settings.linuxdo_client_id or not settings.linuxdo_client_secret:
        raise HTTPException(501, "LinuxDo OAuth not configured")

    oauth = LinuxDoOAuth(
        client_id=settings.linuxdo_client_id,
        client_secret=settings.linuxdo_client_secret,
        redirect_uri=settings.linuxdo_redirect_uri,
    )
    url, state = oauth.build_authorize_url()

    _store_state(state)

    return RedirectResponse(url, status_code=307)


@router.get("/linuxdo/callback")
async def linuxdo_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """LinuxDo OAuth2 callback. Exchanges code for user info, creates/finds user, returns JWT."""
    # Validate state (CSRF)
    if not _validate_and_delete_state(state):
        raise HTTPException(400, "Invalid or expired state parameter")

    if not settings.linuxdo_client_id:
        raise HTTPException(501, "LinuxDo OAuth not configured")

    oauth = LinuxDoOAuth(
        client_id=settings.linuxdo_client_id,
        client_secret=settings.linuxdo_client_secret,
        redirect_uri=settings.linuxdo_redirect_uri,
    )

    try:
        ld_user = await oauth.exchange_code(code)
    except Exception as e:
        raise HTTPException(401, f"LinuxDo authentication failed: {e}")

    try:
        user, _ = await find_or_create_user(
            db, ld_user,
            min_trust_level=settings.linuxdo_min_trust_level,
        )
    except ValueError as e:
        raise HTTPException(403, str(e))

    token = create_token(user.id)

    # Redirect to frontend with token
    frontend_url = settings.cors_origins[0] if settings.cors_origins else "http://localhost:5173"
    return RedirectResponse(f"{frontend_url}/auth/callback?token={token}", status_code=302)
