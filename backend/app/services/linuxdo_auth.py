"""LinuxDo OAuth2 Authorization Code Grant flow."""
import secrets
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.transaction import Transaction

AUTHORIZE_URL = "https://connect.linux.do/oauth2/authorize"
TOKEN_URL = "https://connect.linux.do/oauth2/token"
USER_INFO_URL = "https://connect.linux.do/api/user"


@dataclass
class LinuxDoUser:
    id: int
    username: str
    name: str
    active: bool
    trust_level: int
    silenced: bool


class LinuxDoOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def build_authorize_url(self) -> tuple[str, str]:
        """Build LinuxDo authorize URL. Returns (url, state)."""
        state = secrets.token_urlsafe(24)
        params = urlencode({
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "state": state,
        })
        return f"{AUTHORIZE_URL}?{params}", state

    async def exchange_code(self, code: str) -> LinuxDoUser:
        """Exchange authorization code for access token, then fetch user info."""
        async with httpx.AsyncClient(trust_env=False) as client:
            # Step 1: Exchange code for token (HTTP Basic Auth)
            token_resp = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri,
                },
                auth=(self._client_id, self._client_secret),
                timeout=15,
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            # Step 2: Fetch user info
            user_resp = await client.get(
                USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            user_resp.raise_for_status()
            data = user_resp.json()

        user = LinuxDoUser(
            id=data["id"],
            username=data["username"],
            name=data.get("name") or data["username"],
            active=data["active"],
            trust_level=data["trust_level"],
            silenced=data["silenced"],
        )

        if not user.active or user.silenced:
            raise ValueError("LinuxDo account is inactive or silenced")

        return user


async def find_or_create_user(
    db: AsyncSession,
    ld_user: LinuxDoUser,
    min_trust_level: int = 0,
) -> tuple[User, bool]:
    """Find or create a user from LinuxDo OAuth data. Returns (user, was_created)."""
    if ld_user.trust_level < min_trust_level:
        raise ValueError(
            f"trust_level {ld_user.trust_level} below minimum {min_trust_level}"
        )

    # 1. Find by linuxdo_id
    result = await db.execute(
        select(User).where(User.linuxdo_id == str(ld_user.id))
    )
    user = result.scalar_one_or_none()

    if user:
        # Update trust_level on each login
        user.linuxdo_trust_level = ld_user.trust_level
        await db.commit()
        return user, False

    # 2. Create new user
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        name=ld_user.name,
        email=f"{ld_user.username}@linux.do",
        linuxdo_id=str(ld_user.id),
        linuxdo_trust_level=ld_user.trust_level,
        soul_coin_balance=100,
    )
    db.add(user)
    db.add(Transaction(user_id=user_id, amount=100, reason="signup_bonus"))
    await db.commit()
    await db.refresh(user)
    return user, True
