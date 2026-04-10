import pytest
import io
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.auth_service import verify_token


@pytest.fixture
def auth_headers():
    """Return a valid Authorization header for test user."""
    from app.services.auth_service import create_token
    token = create_token("test-user-upload")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_upload_image_returns_media_url(client, auth_headers, tmp_path):
    """POST /api/media/upload with an image returns a media_url."""
    fake_result = {
        "media_url": "/static/uploads/images/abc123.jpg",
        "media_type": "image",
        "filename": "abc123.jpg",
    }
    with patch("app.routers.media.MediaService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.save_upload = AsyncMock(return_value=fake_result)
        mock_svc_cls.return_value = mock_svc

        image_content = b"\xff\xd8\xff" + b"0" * 50
        files = {"file": ("photo.jpg", io.BytesIO(image_content), "image/jpeg")}
        resp = await client.post(
            "/api/media/upload?media_type=image",
            files=files,
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["media_url"] == "/static/uploads/images/abc123.jpg"
    assert data["media_type"] == "image"


@pytest.mark.anyio
async def test_upload_video_returns_media_url(client, auth_headers):
    """POST /api/media/upload with a video returns a media_url."""
    fake_result = {
        "media_url": "/static/uploads/videos/def456.mp4",
        "media_type": "video",
        "filename": "def456.mp4",
    }
    with patch("app.routers.media.MediaService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.save_upload = AsyncMock(return_value=fake_result)
        mock_svc_cls.return_value = mock_svc

        video_content = b"fakevideo" * 100
        files = {"file": ("clip.mp4", io.BytesIO(video_content), "video/mp4")}
        resp = await client.post(
            "/api/media/upload?media_type=video",
            files=files,
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["media_url"] == "/static/uploads/videos/def456.mp4"


@pytest.mark.anyio
async def test_upload_requires_auth(client):
    """POST /api/media/upload without token returns 401."""
    image_content = b"fakecontent"
    files = {"file": ("photo.jpg", io.BytesIO(image_content), "image/jpeg")}
    resp = await client.post("/api/media/upload?media_type=image", files=files)
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_upload_invalid_media_type_returns_400(client, auth_headers):
    """POST /api/media/upload with unsupported media_type returns 400."""
    from app.media.service import MediaValidationError
    with patch("app.routers.media.MediaService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.save_upload = AsyncMock(
            side_effect=MediaValidationError("Unsupported image type: 'image/bmp'")
        )
        mock_svc_cls.return_value = mock_svc

        files = {"file": ("file.bmp", io.BytesIO(b"fakecontent"), "image/bmp")}
        resp = await client.post(
            "/api/media/upload?media_type=image",
            files=files,
            headers=auth_headers,
        )

    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.anyio
async def test_upload_file_too_large_returns_400(client, auth_headers):
    """POST /api/media/upload with oversized file returns 400."""
    from app.media.service import MediaValidationError
    with patch("app.routers.media.MediaService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.save_upload = AsyncMock(
            side_effect=MediaValidationError("Image too large: 10000000 bytes")
        )
        mock_svc_cls.return_value = mock_svc

        files = {"file": ("big.jpg", io.BytesIO(b"x" * 100), "image/jpeg")}
        resp = await client.post(
            "/api/media/upload?media_type=image",
            files=files,
            headers=auth_headers,
        )

    assert resp.status_code == 400
    assert "too large" in resp.json()["detail"]
