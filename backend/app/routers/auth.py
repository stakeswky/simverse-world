import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.user import RegisterRequest, LoginRequest, AuthResponse, UserResponse
from app.services.auth_service import register_user, login_user, create_token
from app.services.linuxdo_auth import LinuxDoOAuth, find_or_create_user

router = APIRouter(prefix="/auth", tags=["auth"])

# State storage (MVP: in-memory dict. Production: use Redis)
_oauth_states: dict[str, float] = {}  # state -> timestamp

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

    # Store state for CSRF validation
    _oauth_states[state] = time.time()
    # Cleanup old states (> 10 min)
    cutoff = time.time() - 600
    for k in [k for k, v in _oauth_states.items() if v < cutoff]:
        del _oauth_states[k]

    return RedirectResponse(url, status_code=307)


@router.get("/linuxdo/callback")
async def linuxdo_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """LinuxDo OAuth2 callback. Exchanges code for user info, creates/finds user, returns JWT."""
    # Validate state (CSRF)
    if state not in _oauth_states:
        raise HTTPException(400, "Invalid or expired state parameter")
    del _oauth_states[state]

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
