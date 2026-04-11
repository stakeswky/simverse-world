"""GitHub OAuth2 Authorization Code Grant flow."""
import secrets
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.transaction import Transaction

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_INFO_URL = "https://api.github.com/user"


@dataclass
class GitHubUser:
    id: int
    login: str
    name: str
    email: str | None


class GitHubOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def build_authorize_url(self) -> tuple[str, str]:
        state = secrets.token_urlsafe(24)
        params = urlencode({
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        })
        return f"{AUTHORIZE_URL}?{params}", state

    async def exchange_code(self, code: str) -> GitHubUser:
        async with httpx.AsyncClient(trust_env=False) as client:
            token_resp = await client.post(
                TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "redirect_uri": self._redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=15,
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            user_resp = await client.get(
                USER_INFO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=15,
            )
            user_resp.raise_for_status()
            data = user_resp.json()

        return GitHubUser(
            id=data["id"],
            login=data["login"],
            name=data.get("name") or data["login"],
            email=data.get("email"),
        )


async def find_or_create_github_user(
    db: AsyncSession,
    gh_user: GitHubUser,
) -> tuple[User, bool]:
    result = await db.execute(
        select(User).where(User.github_id == str(gh_user.id))
    )
    user = result.scalar_one_or_none()

    if user:
        return user, False

    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        name=gh_user.name,
        email=gh_user.email or f"{gh_user.login}@github.users",
        github_id=str(gh_user.id),
        soul_coin_balance=100,
    )
    db.add(user)
    await db.flush()
    db.add(Transaction(user_id=user_id, amount=100, reason="signup_bonus"))
    await db.commit()
    await db.refresh(user)
    return user, True
