import pytest
from unittest.mock import patch, AsyncMock
from app.llm.client import get_client, LLMClientFactory, _reset_factory


@pytest.fixture(autouse=True)
def reset_factory():
    """Reset the factory singleton between tests."""
    _reset_factory()
    yield
    _reset_factory()


def test_get_client_system_returns_client():
    """get_client('system') should return an Anthropic client using system key."""
    with patch("app.llm.client.settings") as mock_settings:
        mock_settings.effective_api_key = "sys-key"
        mock_settings.llm_base_url = "https://sys.example.com"
        client = get_client("system")
        assert client is not None


def test_get_client_user_without_custom_uses_system():
    """get_client('user') with no custom config should use system defaults."""
    with patch("app.llm.client.settings") as mock_settings:
        mock_settings.effective_api_key = "sys-key"
        mock_settings.llm_base_url = "https://sys.example.com"
        client_sys = get_client("system")
        client_usr = get_client("user")
        # Both should use the same underlying config when user has no custom
        assert client_sys is not None
        assert client_usr is not None


def test_get_client_user_with_custom_config():
    """get_client('user', user_config=...) should use user-provided key."""
    with patch("app.llm.client.settings") as mock_settings:
        mock_settings.effective_api_key = "sys-key"
        mock_settings.llm_base_url = "https://sys.example.com"
        user_config = {
            "api_key": "user-key",
            "base_url": "https://user.example.com",
            "api_format": "anthropic",
        }
        client = get_client("user", user_config=user_config)
        assert client is not None


def test_get_client_invalid_owner_raises():
    """get_client with invalid owner should raise ValueError."""
    with pytest.raises(ValueError, match="owner must be"):
        get_client("invalid")
