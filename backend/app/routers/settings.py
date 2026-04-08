"""Settings router — all /settings/* endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.database import get_db
from app.models.user import User
from app.models.resident import Resident
from app.services.auth_service import get_current_user
from app.services.settings_service import (
    get_effective_settings,
    get_player_resident,
    change_display_name,
    change_password,
    delete_account,
    update_character,
    update_persona,
    patch_settings_group,
    update_reply_mode,
    update_llm_settings,
    test_llm_connection,
)
from app.schemas.settings import (
    AccountSettingsResponse,
    AccountUpdateRequest,
    PasswordChangeRequest,
    CharacterSettingsResponse,
    CharacterUpdateRequest,
    PersonaUpdateRequest,
    InteractionUpdateRequest,
    PrivacyUpdateRequest,
    LLMUpdateRequest,
    LLMTestRequest,
    LLMTestResponse,
    EconomyUpdateRequest,
    AllSettingsResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])


# ─── Auth Helper ─────────────────────────────────────────────────

async def _require_user(request: Request, db: AsyncSession = Depends(get_db)) -> tuple[User, AsyncSession]:
    """Extract and verify JWT from Authorization header. Returns (user, db)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user, db


async def _require_resident(request: Request, db: AsyncSession) -> tuple[User, Resident, AsyncSession]:
    """Get authenticated user and their player resident, or raise 404."""
    user, db = await _require_user(request, db)
    resident = await get_player_resident(db, user)
    if not resident:
        raise HTTPException(status_code=404, detail="No player resident bound to this account")
    return user, resident, db


# ─── GET /settings ───────────────────────────────────────────────

@router.get("", response_model=AllSettingsResponse)
async def get_all_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """GET /settings — return all user settings in one response."""
    user, db = await _require_user(request, db)
    effective = get_effective_settings(user)

    # Account group
    account = AccountSettingsResponse(
        display_name=user.name,
        email=user.email,
        has_password=user.hashed_password is not None,
        github_bound=user.github_id is not None,
        linuxdo_bound=getattr(user, "linuxdo_id", None) is not None,
        linuxdo_trust_level=getattr(user, "linuxdo_trust_level", None),
    )

    # Character group
    resident = await get_player_resident(db, user)
    character = None
    if resident:
        character = CharacterSettingsResponse(
            resident_id=resident.id,
            name=resident.name,
            sprite_key=resident.sprite_key,
            portrait_url=getattr(resident, "portrait_url", None),
            ability_md=resident.ability_md,
            persona_md=resident.persona_md,
            soul_md=resident.soul_md,
        )

    # Interaction — merge reply_mode from Resident
    interaction = effective.get("interaction", {})
    if resident:
        interaction["reply_mode"] = getattr(resident, "reply_mode", "manual")
    else:
        interaction["reply_mode"] = "manual"

    # LLM group — combine column fields + settings_json.llm
    llm_settings = effective.get("llm", {})
    llm_settings.update({
        "custom_llm_enabled": getattr(user, "custom_llm_enabled", False),
        "api_format": getattr(user, "custom_llm_api_format", "anthropic"),
        "api_base_url": getattr(user, "custom_llm_base_url", None),
        "has_api_key": getattr(user, "custom_llm_api_key", None) is not None,
        "model_name": getattr(user, "custom_llm_model", None),
    })

    # Economy group
    economy = effective.get("economy", {})
    economy["soul_coin_balance"] = user.soul_coin_balance

    return AllSettingsResponse(
        account=account,
        character=character,
        interaction=interaction,
        privacy=effective.get("privacy", {}),
        llm=llm_settings,
        economy=economy,
    )


# ─── Account Endpoints ──────────────────────────────────────────

class DeleteAccountRequest(BaseModel):
    confirm_email: str


@router.patch("/account")
async def patch_account(
    req: AccountUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/account — update display name."""
    user, db = await _require_user(request, db)
    if req.display_name is not None:
        user = await change_display_name(db, user, req.display_name)
    return {"display_name": user.name, "email": user.email}


@router.post("/account/password")
async def change_password_endpoint(
    req: PasswordChangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST /settings/account/password — change password (email users only)."""
    user, db = await _require_user(request, db)
    await change_password(db, user, req.old_password, req.new_password)
    return {"message": "Password changed"}


@router.delete("/account")
async def delete_account_endpoint(
    req: DeleteAccountRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """DELETE /settings/account — permanently delete account."""
    user, db = await _require_user(request, db)
    await delete_account(db, user, req.confirm_email)
    return {"message": "Account deleted"}


# ─── Character Endpoints ────────────────────────────────────────

@router.patch("/character", response_model=CharacterSettingsResponse)
async def patch_character(
    req: CharacterUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/character — update character name and/or sprite."""
    user, resident, db = await _require_resident(request, db)
    resident = await update_character(db, resident, name=req.name, sprite_key=req.sprite_key)
    return CharacterSettingsResponse(
        resident_id=resident.id,
        name=resident.name,
        sprite_key=resident.sprite_key,
        portrait_url=getattr(resident, "portrait_url", None),
        ability_md=resident.ability_md,
        persona_md=resident.persona_md,
        soul_md=resident.soul_md,
    )


@router.put("/character/persona", response_model=CharacterSettingsResponse)
async def put_persona(
    req: PersonaUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PUT /settings/character/persona — replace all 3 persona layers."""
    user, resident, db = await _require_resident(request, db)
    resident = await update_persona(db, resident, req.ability_md, req.persona_md, req.soul_md)
    return CharacterSettingsResponse(
        resident_id=resident.id,
        name=resident.name,
        sprite_key=resident.sprite_key,
        portrait_url=getattr(resident, "portrait_url", None),
        ability_md=resident.ability_md,
        persona_md=resident.persona_md,
        soul_md=resident.soul_md,
    )


@router.post("/character/reforge")
async def reforge_character(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /settings/character/reforge — re-run forge pipeline on player resident.
    Delegates to forge_service (Plan 2). Returns 501 if forge not available.
    """
    user, resident, db = await _require_resident(request, db)
    try:
        from app.services.forge_service import start_forge_session
        session = await start_forge_session(db, resident.id, user.id)
        return {"message": "Reforge started", "forge_session_id": session.id}
    except (ImportError, AttributeError):
        raise HTTPException(status_code=501, detail="Forge pipeline not available yet")


@router.post("/character/import")
async def import_skill_file(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /settings/character/import — import a Skill JSON file.
    Expects JSON body with skill data. Stub endpoint; full implementation in Plan 2.
    """
    user, resident, db = await _require_resident(request, db)
    body = await request.json()
    if not body:
        raise HTTPException(status_code=422, detail="Empty skill data")
    # Apply persona fields from imported skill
    if "ability_md" in body:
        resident.ability_md = body["ability_md"]
    if "persona_md" in body:
        resident.persona_md = body["persona_md"]
    if "soul_md" in body:
        resident.soul_md = body["soul_md"]
    if "name" in body:
        resident.name = body["name"]
    await db.commit()
    await db.refresh(resident)
    return {"message": "Skill imported", "resident_id": resident.id, "name": resident.name}


@router.post("/character/avatar")
async def regenerate_or_upload_avatar(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /settings/character/avatar — regenerate AI portrait or upload custom.
    Delegates to portrait_service (Plan 4). Returns 501 if not available.
    """
    user, resident, db = await _require_resident(request, db)
    try:
        from app.services.portrait_service import generate_portrait
        portrait_url = await generate_portrait(resident)
        resident.portrait_url = portrait_url
        await db.commit()
        await db.refresh(resident)
        return {"portrait_url": portrait_url}
    except (ImportError, AttributeError):
        raise HTTPException(status_code=501, detail="Portrait service not available yet")


# ─── Interaction / Privacy / Economy Endpoints ───────────────────

@router.patch("/interaction")
async def patch_interaction(
    req: InteractionUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/interaction — update interaction preferences."""
    user, db = await _require_user(request, db)

    # reply_mode lives on Resident, not settings_json
    if req.reply_mode is not None:
        resident = await get_player_resident(db, user)
        if resident:
            await update_reply_mode(db, resident, req.reply_mode)

    # Other interaction fields go into settings_json
    updates = req.model_dump(exclude_none=True, exclude={"reply_mode"})
    if updates:
        await patch_settings_group(db, user, "interaction", updates)

    # Return full effective settings so frontend can refresh
    await db.refresh(user)
    effective = get_effective_settings(user)
    interaction = effective.get("interaction", {})
    # Merge in reply_mode from Resident
    resident = await get_player_resident(db, user)
    interaction["reply_mode"] = getattr(resident, "reply_mode", "manual") if resident else "manual"

    return {"interaction": interaction}


@router.patch("/privacy")
async def patch_privacy(
    req: PrivacyUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/privacy — update privacy preferences."""
    user, db = await _require_user(request, db)
    updates = req.model_dump(exclude_none=True)
    if updates:
        await patch_settings_group(db, user, "privacy", updates)
    await db.refresh(user)
    effective = get_effective_settings(user)
    return {"privacy": effective.get("privacy", {})}


@router.patch("/economy")
async def patch_economy(
    req: EconomyUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/economy — update economy preferences."""
    user, db = await _require_user(request, db)
    updates = req.model_dump(exclude_none=True)
    if updates:
        await patch_settings_group(db, user, "economy", updates)
    await db.refresh(user)
    effective = get_effective_settings(user)
    economy = effective.get("economy", {})
    economy["soul_coin_balance"] = user.soul_coin_balance
    return {"economy": economy}


# ─── LLM Endpoints ──────────────────────────────────────────────

@router.patch("/llm")
async def patch_llm(
    req: LLMUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/llm — update custom LLM configuration."""
    user, db = await _require_user(request, db)
    user = await update_llm_settings(
        db,
        user,
        custom_llm_enabled=req.custom_llm_enabled,
        api_format=req.api_format,
        api_base_url=req.api_base_url,
        api_key=req.api_key,
        model_name=req.model_name,
        thinking_enabled=req.thinking_enabled,
        temperature=req.temperature,
    )
    effective = get_effective_settings(user)
    llm = effective.get("llm", {})
    llm.update({
        "custom_llm_enabled": user.custom_llm_enabled,
        "api_format": user.custom_llm_api_format,
        "api_base_url": user.custom_llm_base_url,
        "has_api_key": user.custom_llm_api_key is not None,
        "model_name": user.custom_llm_model,
    })
    return llm


@router.post("/llm/test", response_model=LLMTestResponse)
async def test_llm_endpoint(
    req: LLMTestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST /settings/llm/test — test custom LLM connection."""
    await _require_user(request, db)  # auth only
    result = await test_llm_connection(
        api_format=req.api_format,
        api_base_url=req.api_base_url,
        api_key=req.api_key,
        model_name=req.model_name,
    )
    return LLMTestResponse(**result)


# ─── OAuth Bind/Unbind ──────────────────────────────────────────

@router.post("/account/bind-github")
async def bind_github(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST /settings/account/bind-github — initiate GitHub OAuth binding flow."""
    user, db = await _require_user(request, db)
    if not app_settings.github_client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")
    authorize_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={app_settings.github_client_id}"
        f"&scope=read:user user:email"
        f"&state=bind:{user.id}"
    )
    return {"authorize_url": authorize_url}


@router.post("/account/bind-linuxdo")
async def bind_linuxdo(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST /settings/account/bind-linuxdo — initiate LinuxDo OAuth binding flow."""
    user, db = await _require_user(request, db)
    try:
        from app.services.linuxdo_auth import LinuxDoOAuth
        from app.config import settings as cfg
        oauth = LinuxDoOAuth(
            client_id=getattr(cfg, "linuxdo_client_id", ""),
            client_secret=getattr(cfg, "linuxdo_client_secret", ""),
            redirect_uri=getattr(cfg, "linuxdo_redirect_uri", ""),
        )
        if not oauth.client_id:
            raise HTTPException(status_code=501, detail="LinuxDo OAuth not configured")
        url, state = oauth.build_authorize_url()
        return {"authorize_url": url, "state": state}
    except ImportError:
        raise HTTPException(status_code=501, detail="LinuxDo OAuth not available yet")


@router.delete("/account/unbind/{provider}")
async def unbind_provider(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """DELETE /settings/account/unbind/{provider} — unbind a third-party account."""
    user, db = await _require_user(request, db)

    if provider == "github":
        if not user.github_id:
            raise HTTPException(status_code=400, detail="GitHub not bound")
        if not user.hashed_password and not getattr(user, "linuxdo_id", None):
            raise HTTPException(
                status_code=400,
                detail="Cannot unbind GitHub — it is your only login method",
            )
        user.github_id = None
        await db.commit()
        return {"message": "GitHub unbound"}

    elif provider == "linuxdo":
        if not getattr(user, "linuxdo_id", None):
            raise HTTPException(status_code=400, detail="LinuxDo not bound")
        if not user.hashed_password and not user.github_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot unbind LinuxDo — it is your only login method",
            )
        user.linuxdo_id = None  # type: ignore[assignment]
        user.linuxdo_trust_level = None  # type: ignore[assignment]
        await db.commit()
        return {"message": "LinuxDo unbound"}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
