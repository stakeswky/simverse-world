"""Tests for user settings: schemas, service helpers, and API endpoints."""
import pytest
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError

import httpx

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
from app.services.settings_service import merge_settings_json, build_settings_defaults
from app.models.user import User
from app.models.resident import Resident
from app.services.auth_service import create_token, pwd_context


# ─── Task 1: Schema Validation Tests ─────────────────────────────


def test_account_update_request_optional_fields():
    """All fields should be optional for PATCH semantics."""
    req = AccountUpdateRequest()
    assert req.display_name is None

    req2 = AccountUpdateRequest(display_name="New Name")
    assert req2.display_name == "New Name"


def test_password_change_requires_both_fields():
    """Password change must have old and new password."""
    with pytest.raises(ValidationError):
        PasswordChangeRequest(old_password="abc")  # missing new_password

    req = PasswordChangeRequest(old_password="old", new_password="newpassword123")
    assert req.new_password == "newpassword123"


def test_persona_update_request_all_layers():
    """Persona update accepts 3-layer markdown."""
    req = PersonaUpdateRequest(
        ability_md="# Abilities",
        persona_md="# Persona",
        soul_md="# Soul",
    )
    assert req.ability_md == "# Abilities"


def test_privacy_update_validates_enum():
    """persona_visibility must be one of the allowed values."""
    req = PrivacyUpdateRequest(persona_visibility="full")
    assert req.persona_visibility == "full"

    with pytest.raises(ValidationError):
        PrivacyUpdateRequest(persona_visibility="invalid_value")


def test_llm_update_validates_api_format():
    """api_format must be openai or anthropic."""
    req = LLMUpdateRequest(api_format="openai")
    assert req.api_format == "openai"

    with pytest.raises(ValidationError):
        LLMUpdateRequest(api_format="gemini")


def test_economy_update_threshold():
    """Low balance alert threshold must be non-negative."""
    req = EconomyUpdateRequest(low_balance_alert=10)
    assert req.low_balance_alert == 10

    with pytest.raises(ValidationError):
        EconomyUpdateRequest(low_balance_alert=-5)


def test_all_settings_response_structure():
    """AllSettingsResponse should compose all sub-groups."""
    resp = AllSettingsResponse(
        account=AccountSettingsResponse(
            display_name="Alice",
            email="a@b.com",
            has_password=True,
            github_bound=False,
            linuxdo_bound=False,
            linuxdo_trust_level=None,
        ),
        character=None,
        interaction={"reply_mode": "manual", "offline_auto_reply": False, "notifications": {}},
        privacy={"map_visible": True, "persona_visibility": "full", "allow_conversation_stats": True},
        llm={"custom_llm_enabled": False},
        economy={"soul_coin_balance": 100, "low_balance_alert": 10},
    )
    assert resp.account.display_name == "Alice"
    assert resp.character is None


# ─── Task 2: Service Helper Tests ────────────────────────────────


def test_merge_settings_json_adds_new_keys():
    """Deep merge should add new keys without clobbering existing."""
    existing = {"interaction": {"reply_mode": "manual"}, "privacy": {"map_visible": True}}
    patch = {"interaction": {"offline_auto_reply": True}}
    result = merge_settings_json(existing, patch)
    assert result["interaction"]["reply_mode"] == "manual"
    assert result["interaction"]["offline_auto_reply"] is True
    assert result["privacy"]["map_visible"] is True


def test_merge_settings_json_overwrites_existing():
    """Deep merge should overwrite scalar values."""
    existing = {"privacy": {"map_visible": True, "persona_visibility": "full"}}
    patch = {"privacy": {"map_visible": False}}
    result = merge_settings_json(existing, patch)
    assert result["privacy"]["map_visible"] is False
    assert result["privacy"]["persona_visibility"] == "full"


def test_merge_settings_json_empty_existing():
    """Merge into empty dict should work."""
    result = merge_settings_json({}, {"economy": {"low_balance_alert": 10}})
    assert result["economy"]["low_balance_alert"] == 10


def test_build_settings_defaults():
    """Should return complete defaults for all groups."""
    defaults = build_settings_defaults()
    assert "interaction" in defaults
    assert "privacy" in defaults
    assert "economy" in defaults
    assert "llm" in defaults
    assert defaults["interaction"]["offline_auto_reply"] is False
    assert defaults["privacy"]["map_visible"] is True
    assert defaults["privacy"]["persona_visibility"] == "full"
    assert defaults["privacy"]["allow_conversation_stats"] is True
    assert defaults["economy"]["low_balance_alert"] == 10
    assert defaults["llm"]["thinking_enabled"] is False
    assert defaults["llm"]["temperature"] == 0.7


# ─── Task 3: API Endpoint Tests ──────────────────────────────────


@pytest.fixture
async def auth_user(db_session) -> tuple[User, str]:
    """Create a user with password + player resident and return (user, token)."""
    user = User(
        name="TestUser",
        email="test@example.com",
        hashed_password=pwd_context.hash("oldpassword123"),
        settings_json={},
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resident = Resident(
        slug="player-test",
        name="PlayerChar",
        creator_id=user.id,
        resident_type="player",
        sprite_key="伊莎贝拉",
        ability_md="# Ability",
        persona_md="# Persona",
        soul_md="# Soul",
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    user.player_resident_id = resident.id
    await db_session.commit()
    await db_session.refresh(user)

    token = create_token(user.id)
    return user, token


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_get_all_settings(client, auth_user):
    """GET /settings should return composite settings for authenticated user."""
    _, token = auth_user
    resp = await client.get("/settings", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "account" in data
    assert data["account"]["display_name"] == "TestUser"
    assert data["account"]["has_password"] is True
    assert data["account"]["github_bound"] is False
    assert "character" in data
    assert data["character"]["name"] == "PlayerChar"
    assert "interaction" in data
    assert "privacy" in data
    assert "llm" in data
    assert "economy" in data
    assert data["economy"]["soul_coin_balance"] == 100


async def test_get_settings_unauthenticated(client):
    """GET /settings without token should return 401."""
    resp = await client.get("/settings")
    assert resp.status_code == 401


async def test_patch_account_display_name(client, auth_user):
    """PATCH /settings/account should update display name."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/account",
        json={"display_name": "NewName"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "NewName"


async def test_patch_account_change_password(client, auth_user):
    """PATCH /settings/account/password should change password."""
    _, token = auth_user
    resp = await client.post(
        "/settings/account/password",
        json={"old_password": "oldpassword123", "new_password": "newpassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Password changed"


async def test_change_password_wrong_old(client, auth_user):
    """Wrong old password should return 403."""
    _, token = auth_user
    resp = await client.post(
        "/settings/account/password",
        json={"old_password": "wrongpassword", "new_password": "newpassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_patch_character_name(client, auth_user):
    """PATCH /settings/character should update character name."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/character",
        json={"name": "NewCharName"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewCharName"


async def test_put_persona(client, auth_user):
    """PUT /settings/character/persona should replace all 3 layers."""
    _, token = auth_user
    resp = await client.put(
        "/settings/character/persona",
        json={
            "ability_md": "# New Ability",
            "persona_md": "# New Persona",
            "soul_md": "# New Soul",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ability_md"] == "# New Ability"
    assert data["persona_md"] == "# New Persona"
    assert data["soul_md"] == "# New Soul"


async def test_patch_character_no_resident(client, db_session):
    """PATCH /settings/character should 404 when user has no player resident."""
    user = User(name="NoResident", email="nores@test.com", settings_json={})
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_token(user.id)

    resp = await client.patch(
        "/settings/character",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "player resident" in resp.json()["detail"].lower()


async def test_patch_interaction_settings(client, auth_user):
    """PATCH /settings/interaction should update interaction prefs."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/interaction",
        json={"offline_auto_reply": True, "notification_chat": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["interaction"]["offline_auto_reply"] is True
    assert data["interaction"]["notification_chat"] is False
    assert data["interaction"]["notification_system"] is True


async def test_patch_interaction_reply_mode(client, auth_user):
    """PATCH /settings/interaction with reply_mode should update Resident.reply_mode."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/interaction",
        json={"reply_mode": "auto"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["interaction"]["reply_mode"] == "auto"


async def test_patch_privacy_settings(client, auth_user):
    """PATCH /settings/privacy should update privacy prefs."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/privacy",
        json={"map_visible": False, "persona_visibility": "hidden"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["privacy"]["map_visible"] is False
    assert data["privacy"]["persona_visibility"] == "hidden"
    assert data["privacy"]["allow_conversation_stats"] is True


async def test_patch_economy_settings(client, auth_user):
    """PATCH /settings/economy should update economy prefs."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/economy",
        json={"low_balance_alert": 50},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["economy"]["low_balance_alert"] == 50


async def test_patch_llm_settings(client, auth_user):
    """PATCH /settings/llm should update custom LLM config."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/llm",
        json={
            "custom_llm_enabled": True,
            "api_format": "openai",
            "api_base_url": "https://api.example.com",
            "model_name": "gpt-4o",
            "temperature": 0.9,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["custom_llm_enabled"] is True
    assert data["api_format"] == "openai"
    assert data["api_base_url"] == "https://api.example.com"
    assert data["model_name"] == "gpt-4o"
    assert data["temperature"] == 0.9


async def test_patch_llm_invalid_format(client, auth_user):
    """PATCH /settings/llm with invalid api_format should 422."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/llm",
        json={"api_format": "invalid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_llm_test_connection_success(client, auth_user):
    """POST /settings/llm/test should test the LLM endpoint."""
    _, token = auth_user

    mock_response = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "connection ok"}}],
        },
        request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
    )

    with patch("app.services.settings_service.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/settings/llm/test",
            json={
                "api_format": "openai",
                "api_base_url": "https://api.example.com",
                "api_key": "sk-test",
                "model_name": "gpt-4o",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["model_response"] == "connection ok"


async def test_llm_test_connection_timeout(client, auth_user):
    """POST /settings/llm/test should handle timeout gracefully."""
    _, token = auth_user

    with patch("app.services.settings_service.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.TimeoutException("timed out")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/settings/llm/test",
            json={
                "api_format": "openai",
                "api_base_url": "https://api.example.com",
                "api_key": "sk-test",
                "model_name": "gpt-4o",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "timed out" in data["error"].lower()


async def test_unbind_github_no_binding(client, auth_user):
    """DELETE /settings/account/unbind/github should 400 when not bound."""
    _, token = auth_user
    resp = await client.delete(
        "/settings/account/unbind/github",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "not bound" in resp.json()["detail"].lower()


async def test_unbind_invalid_provider(client, auth_user):
    """DELETE /settings/account/unbind/invalid should 400."""
    _, token = auth_user
    resp = await client.delete(
        "/settings/account/unbind/invalid",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


async def test_settings_round_trip(client, auth_user):
    """Full round-trip: read settings, modify each group, verify changes persist."""
    _, token = auth_user
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Read initial
    resp = await client.get("/settings", headers=headers)
    assert resp.status_code == 200
    initial = resp.json()
    assert initial["account"]["display_name"] == "TestUser"

    # 2. Modify account
    await client.patch("/settings/account", json={"display_name": "RoundTrip"}, headers=headers)

    # 3. Modify privacy
    await client.patch("/settings/privacy", json={"map_visible": False}, headers=headers)

    # 4. Modify economy
    await client.patch("/settings/economy", json={"low_balance_alert": 99}, headers=headers)

    # 5. Read again — all changes should be reflected
    resp = await client.get("/settings", headers=headers)
    assert resp.status_code == 200
    final = resp.json()
    assert final["account"]["display_name"] == "RoundTrip"
    assert final["privacy"]["map_visible"] is False
    assert final["economy"]["low_balance_alert"] == 99
    assert final["privacy"]["allow_conversation_stats"] is True
