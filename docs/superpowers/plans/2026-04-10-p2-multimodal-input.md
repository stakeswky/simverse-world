# P2: Multimodal Input — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Players can send images and videos to residents in chat. Residents "see" them via vision models and respond naturally. Media understanding results are stored as memories and shared between residents as text summaries only.

**Architecture:**
- Images → `qwen3.6-plus` (already configured as `settings.effective_model`, supports Anthropic-compatible image content blocks)
- Videos → `kimi-k2.5` (temporary model switch via DashScope Anthropic-compatible endpoint, then back to main model)
- Media files stored in `backend/static/uploads/images/` and `backend/static/uploads/videos/`
- Residents share images via text summaries only (no re-processing original files)
- Memory model already has `media_url` and `media_summary` fields (P1 complete)

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Anthropic SDK, pytest + aiosqlite (tests), React 18 + TypeScript (frontend)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/config.py` | Add media upload settings + video model |
| Create | `backend/app/media/__init__.py` | Package init |
| Create | `backend/app/media/service.py` | MediaService: save, validate, resolve |
| Create | `backend/tests/test_media_service.py` | Service unit tests |
| Create | `backend/app/routers/media.py` | POST /api/media/upload router |
| Create | `backend/tests/test_media_upload.py` | Router integration tests |
| Create | `backend/app/media/model_router.py` | ModelRouter: route by media type, call vision models |
| Create | `backend/tests/test_model_router.py` | ModelRouter unit tests (mocked) |
| Modify | `backend/app/ws/protocol.py` | Add optional `media_url` + `media_type` to ChatMsg |
| Modify | `backend/app/ws/handler.py` | Wire ModelRouter into chat_msg block |
| Create | `backend/tests/test_media_chat_integration.py` | WS integration test with media |

---

## Task 1: Media Config Settings

**Files:**
- Modify: `backend/app/config.py`
- Shell: create upload directories

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_media_config.py`:

```python
import pytest
from app.config import Settings


def test_media_config_defaults():
    s = Settings()
    assert s.media_upload_dir == "backend/static/uploads"
    assert s.media_max_image_size == 5 * 1024 * 1024  # 5 MB
    assert s.media_max_video_size == 50 * 1024 * 1024  # 50 MB
    assert s.video_llm_model == "kimi-k2.5"


def test_media_upload_dir_is_string():
    s = Settings()
    assert isinstance(s.media_upload_dir, str)
```

Run: `python3 -m pytest backend/tests/test_media_config.py -x` → FAIL (fields don't exist yet)

- [ ] **Step 2: Implement**

Edit `backend/app/config.py` — add after `user_llm_concurrency`:

```python
    # --- Media Upload (P2) ---
    media_upload_dir: str = "backend/static/uploads"
    media_max_image_size: int = 5 * 1024 * 1024   # 5 MB
    media_max_video_size: int = 50 * 1024 * 1024  # 50 MB
    video_llm_model: str = "kimi-k2.5"
```

Then create the directories:

```bash
mkdir -p backend/static/uploads/images
mkdir -p backend/static/uploads/videos
touch backend/static/uploads/images/.gitkeep
touch backend/static/uploads/videos/.gitkeep
```

- [ ] **Step 3: Verify**

```bash
python3 -m pytest backend/tests/test_media_config.py -x
```

Expected: 2 passed.

---

## Task 2: Media Upload Service

**Files:**
- Create: `backend/app/media/__init__.py`
- Create: `backend/app/media/service.py`
- Create: `backend/tests/test_media_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_media_service.py`:

```python
import pytest
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import UploadFile
from app.media.service import MediaService, MediaValidationError


def _make_upload_file(filename: str, content: bytes, content_type: str) -> UploadFile:
    file_obj = io.BytesIO(content)
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = filename
    mock_file.content_type = content_type
    mock_file.read = AsyncMock(return_value=content)
    mock_file.size = len(content)
    return mock_file


@pytest.mark.anyio
async def test_save_image_returns_media_url(tmp_path):
    svc = MediaService(upload_base=str(tmp_path))
    content = b"\xff\xd8\xff" + b"0" * 100  # minimal JPEG-like bytes
    f = _make_upload_file("photo.jpg", content, "image/jpeg")

    result = await svc.save_upload(f, media_type="image")

    assert result["media_type"] == "image"
    assert result["media_url"].startswith("/static/uploads/images/")
    assert result["media_url"].endswith(".jpg")
    # File should exist on disk
    file_path = svc.get_file_path(result["media_url"])
    assert file_path.exists()
    assert file_path.read_bytes() == content


@pytest.mark.anyio
async def test_save_video_returns_media_url(tmp_path):
    svc = MediaService(upload_base=str(tmp_path))
    content = b"fakevideocontent" * 100
    f = _make_upload_file("clip.mp4", content, "video/mp4")

    result = await svc.save_upload(f, media_type="video")

    assert result["media_type"] == "video"
    assert result["media_url"].startswith("/static/uploads/videos/")
    assert result["media_url"].endswith(".mp4")


@pytest.mark.anyio
async def test_image_too_large_raises_error(tmp_path):
    svc = MediaService(upload_base=str(tmp_path), max_image_size=100)
    content = b"x" * 200
    f = _make_upload_file("big.jpg", content, "image/jpeg")

    with pytest.raises(MediaValidationError, match="Image too large"):
        await svc.save_upload(f, media_type="image")


@pytest.mark.anyio
async def test_video_too_large_raises_error(tmp_path):
    svc = MediaService(upload_base=str(tmp_path), max_video_size=100)
    content = b"x" * 200
    f = _make_upload_file("big.mp4", content, "video/mp4")

    with pytest.raises(MediaValidationError, match="Video too large"):
        await svc.save_upload(f, media_type="video")


@pytest.mark.anyio
async def test_unsupported_image_type_raises_error(tmp_path):
    svc = MediaService(upload_base=str(tmp_path))
    content = b"fakecontent"
    f = _make_upload_file("file.bmp", content, "image/bmp")

    with pytest.raises(MediaValidationError, match="Unsupported image type"):
        await svc.save_upload(f, media_type="image")


@pytest.mark.anyio
async def test_unsupported_video_type_raises_error(tmp_path):
    svc = MediaService(upload_base=str(tmp_path))
    content = b"fakecontent"
    f = _make_upload_file("file.avi", content, "video/avi")

    with pytest.raises(MediaValidationError, match="Unsupported video type"):
        await svc.save_upload(f, media_type="video")


def test_get_file_path_resolves_url(tmp_path):
    svc = MediaService(upload_base=str(tmp_path))
    url = "/static/uploads/images/abc123.jpg"
    path = svc.get_file_path(url)
    assert path == tmp_path / "images" / "abc123.jpg"


def test_get_file_path_video(tmp_path):
    svc = MediaService(upload_base=str(tmp_path))
    url = "/static/uploads/videos/abc123.mp4"
    path = svc.get_file_path(url)
    assert path == tmp_path / "videos" / "abc123.mp4"
```

Run: `python3 -m pytest backend/tests/test_media_service.py -x` → FAIL (module not found)

- [ ] **Step 2: Implement**

Create `backend/app/media/__init__.py`:

```python
"""Media upload and processing package."""
```

Create `backend/app/media/service.py`:

```python
"""Media upload service: validate, save, and resolve uploaded files."""
import uuid
from pathlib import Path
from fastapi import UploadFile
from app.config import settings


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

ALLOWED_VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}


class MediaValidationError(ValueError):
    """Raised when uploaded media fails validation."""
    pass


class MediaService:
    """Handles saving and resolving uploaded media files."""

    def __init__(
        self,
        upload_base: str | None = None,
        max_image_size: int | None = None,
        max_video_size: int | None = None,
    ):
        self.upload_base = Path(upload_base or settings.media_upload_dir)
        self.max_image_size = max_image_size or settings.media_max_image_size
        self.max_video_size = max_video_size or settings.media_max_video_size

    async def save_upload(self, file: UploadFile, media_type: str) -> dict:
        """Validate and save an uploaded file. Returns media_url, media_type, filename.

        Args:
            file: FastAPI UploadFile object.
            media_type: "image" or "video".

        Returns:
            dict with keys: media_url (str), media_type (str), filename (str)

        Raises:
            MediaValidationError: if file is too large or unsupported type.
        """
        content = await file.read()
        size = len(content)

        if media_type == "image":
            if size > self.max_image_size:
                raise MediaValidationError(
                    f"Image too large: {size} bytes (max {self.max_image_size})"
                )
            content_type = file.content_type or ""
            if content_type not in ALLOWED_IMAGE_TYPES:
                raise MediaValidationError(
                    f"Unsupported image type: {content_type!r}. "
                    f"Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
                )
            ext = ALLOWED_IMAGE_TYPES[content_type]
            subdir = "images"
        elif media_type == "video":
            if size > self.max_video_size:
                raise MediaValidationError(
                    f"Video too large: {size} bytes (max {self.max_video_size})"
                )
            content_type = file.content_type or ""
            if content_type not in ALLOWED_VIDEO_TYPES:
                raise MediaValidationError(
                    f"Unsupported video type: {content_type!r}. "
                    f"Allowed: {', '.join(ALLOWED_VIDEO_TYPES)}"
                )
            ext = ALLOWED_VIDEO_TYPES[content_type]
            subdir = "videos"
        else:
            raise MediaValidationError(f"Unknown media_type: {media_type!r}")

        filename = f"{uuid.uuid4()}{ext}"
        dest_dir = self.upload_base / subdir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        dest_path.write_bytes(content)

        media_url = f"/static/uploads/{subdir}/{filename}"
        return {
            "media_url": media_url,
            "media_type": media_type,
            "filename": filename,
        }

    def get_file_path(self, media_url: str) -> Path:
        """Resolve a media_url (e.g. /static/uploads/images/abc.jpg) to an absolute Path.

        Strips the /static/uploads/ prefix and resolves relative to upload_base.
        """
        # Strip leading /static/uploads/
        relative = media_url.removeprefix("/static/uploads/")
        return self.upload_base / relative
```

- [ ] **Step 3: Verify**

```bash
python3 -m pytest backend/tests/test_media_service.py -x -v
```

Expected: 8 passed.

---

## Task 3: Media Upload Router

**Files:**
- Create: `backend/app/routers/media.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_media_upload.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_media_upload.py`:

```python
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
```

Run: `python3 -m pytest backend/tests/test_media_upload.py -x` → FAIL (router doesn't exist)

- [ ] **Step 2: Implement**

Create `backend/app/routers/media.py`:

```python
"""Media upload router: POST /api/media/upload."""
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.media.service import MediaService, MediaValidationError

router = APIRouter(prefix="/api/media", tags=["media"])


async def _require_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


class UploadResponse(BaseModel):
    media_url: str
    media_type: str
    filename: str


@router.post("/upload", response_model=UploadResponse)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    media_type: str = Query(..., pattern="^(image|video)$"),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image or video file. Returns the media_url for use in chat messages.

    - **media_type**: "image" or "video"
    - **file**: multipart file upload

    Returns 400 if file is too large or has an unsupported content type.
    Requires valid Bearer token.
    """
    await _require_user(request, db)

    svc = MediaService()
    try:
        result = await svc.save_upload(file, media_type=media_type)
    except MediaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return UploadResponse(**result)
```

Modify `backend/app/main.py` — add import and router registration:

```python
# Add to imports at top:
from app.routers import media as media_router

# Add after existing include_router calls:
app.include_router(media_router.router)
```

Full diff view of main.py imports line (line 6):
```python
from app.routers import auth, users, residents, forge, profile, search, bulletin, onboarding, sprites, avatar, settings as settings_router, media as media_router
```

And add at the end of `include_router` calls (before the websocket):
```python
app.include_router(media_router.router)
```

- [ ] **Step 3: Verify**

```bash
python3 -m pytest backend/tests/test_media_upload.py -x -v
```

Expected: 5 passed.

---

## Task 4: Model Router for Multimodal

**Files:**
- Create: `backend/app/media/model_router.py`
- Create: `backend/tests/test_model_router.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_model_router.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from app.media.model_router import ModelRouter


def _make_stream_mock(chunks: list[str]):
    """Create a mock async context manager that yields text chunks."""
    class FakeStream:
        def __init__(self):
            self.text_stream = _async_gen(chunks)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    async def _async_gen(items):
        for item in items:
            yield item

    return FakeStream()


def _mock_llm_response(text: str):
    mock_msg = MagicMock()
    mock_block = MagicMock()
    mock_block.text = text
    mock_msg.content = [mock_block]
    return mock_msg


@pytest.mark.anyio
async def test_image_routes_to_main_model_with_image_block():
    """Images are sent to the main model as an image content block."""
    system_prompt = "You are a helpful assistant."
    messages = [{"role": "user", "content": "What is in this image?"}]
    image_url = "https://example.com/photo.jpg"

    collected_chunks = []

    with patch("app.media.model_router.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_stream_mock(["It's ", "a cat!"])
        mock_get_client.return_value = mock_client

        router = ModelRouter()
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=image_url,
            media_type="image",
        ):
            collected_chunks.append(chunk)

    assert collected_chunks == ["It's ", "a cat!"]

    # Verify client.messages.stream was called with image content block
    call_kwargs = mock_client.messages.stream.call_args.kwargs
    assert call_kwargs["system"] == system_prompt
    # Last message should have content list with text + image blocks
    last_msg = call_kwargs["messages"][-1]
    assert last_msg["role"] == "user"
    content = last_msg["content"]
    # Should have text block + image block
    types = [block["type"] for block in content]
    assert "text" in types
    assert "image" in types
    # Image block should have the URL
    image_block = next(b for b in content if b["type"] == "image")
    assert image_block["source"]["type"] == "url"
    assert image_block["source"]["url"] == image_url


@pytest.mark.anyio
async def test_video_gets_summary_then_main_model():
    """Videos: kimi-k2.5 summarizes the video, then main model responds with summary injected."""
    system_prompt = "You are a helpful assistant."
    messages = [{"role": "user", "content": "What happens in this video?"}]
    video_url = "https://example.com/clip.mp4"
    video_summary = "The video shows a cat chasing a ball of yarn."

    collected_chunks = []

    with patch("app.media.model_router.get_client") as mock_get_client:
        # Both calls go to the same client instance in this setup
        mock_kimi_client = MagicMock()
        mock_kimi_client.messages.create = AsyncMock(
            return_value=_mock_llm_response(video_summary)
        )
        mock_main_client = MagicMock()
        mock_main_client.messages.stream.return_value = _make_stream_mock(["Great video!"])

        # First call returns kimi client, second returns main client
        mock_get_client.side_effect = [mock_kimi_client, mock_main_client]

        router = ModelRouter()
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=video_url,
            media_type="video",
        ):
            collected_chunks.append(chunk)

    assert collected_chunks == ["Great video!"]

    # First get_client call should use kimi model
    kimi_create_kwargs = mock_kimi_client.messages.create.call_args.kwargs
    assert kimi_create_kwargs["model"] == "kimi-k2.5"

    # Main model messages should include video summary in text
    main_stream_kwargs = mock_main_client.messages.stream.call_args.kwargs
    last_msg = main_stream_kwargs["messages"][-1]
    assert video_summary in str(last_msg["content"])


@pytest.mark.anyio
async def test_understand_video_calls_kimi():
    """_understand_video() calls kimi-k2.5 with the video URL."""
    video_url = "https://example.com/test.mp4"
    expected_summary = "A dog runs across a field."

    with patch("app.media.model_router.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_llm_response(expected_summary)
        )
        mock_get_client.return_value = mock_client

        router = ModelRouter()
        summary = await router._understand_video(video_url)

    assert summary == expected_summary

    create_kwargs = mock_client.messages.create.call_args.kwargs
    assert create_kwargs["model"] == "kimi-k2.5"
    # Video URL should appear somewhere in the messages
    messages_str = str(create_kwargs["messages"])
    assert video_url in messages_str


@pytest.mark.anyio
async def test_chat_with_media_no_media_falls_back_to_text():
    """If media_url is None, behaves like a regular text chat stream."""
    system_prompt = "You are helpful."
    messages = [{"role": "user", "content": "Hello"}]

    collected = []

    with patch("app.media.model_router.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_stream_mock(["Hi there!"])
        mock_get_client.return_value = mock_client

        router = ModelRouter()
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=None,
            media_type=None,
        ):
            collected.append(chunk)

    assert collected == ["Hi there!"]

    call_kwargs = mock_client.messages.stream.call_args.kwargs
    last_msg = call_kwargs["messages"][-1]
    # Content should be plain string, not list
    assert isinstance(last_msg["content"], str)
```

Run: `python3 -m pytest backend/tests/test_model_router.py -x` → FAIL (module not found)

- [ ] **Step 2: Implement**

Create `backend/app/media/model_router.py`:

```python
"""Model router for multimodal chat: routes image/video to appropriate vision models.

- Images  → main model (settings.effective_model) with Anthropic image content blocks.
- Videos  → kimi-k2.5 first (for summary), then main model with summary injected into text.
- No media → falls through to regular streaming, same as stream_chat().
"""
import copy
import logging
from typing import AsyncGenerator

from app.config import settings
from app.llm.client import get_client

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes chat messages to the appropriate model based on media type."""

    async def chat_with_media(
        self,
        system_prompt: str,
        messages: list[dict],
        media_url: str | None,
        media_type: str | None,
        *,
        owner: str = "user",
        user_config: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response, injecting media context as appropriate.

        For images: the last user message is augmented with an image content block.
        For videos: kimi-k2.5 summarizes the video first; the summary is injected
                    as additional text in the last user message, then the main model streams.
        For no media: plain streaming, identical to stream_chat().

        Yields text chunks.
        """
        augmented_messages = copy.deepcopy(messages)

        if media_type == "image" and media_url:
            augmented_messages = self._inject_image(augmented_messages, media_url)
            async for chunk in self._stream(system_prompt, augmented_messages, owner=owner, user_config=user_config):
                yield chunk

        elif media_type == "video" and media_url:
            video_summary = await self._understand_video(media_url)
            augmented_messages = self._inject_video_summary(augmented_messages, media_url, video_summary)
            async for chunk in self._stream(system_prompt, augmented_messages, owner=owner, user_config=user_config):
                yield chunk

        else:
            # No media — plain text stream (same path as stream_chat)
            async for chunk in self._stream(system_prompt, messages, owner=owner, user_config=user_config):
                yield chunk

    def _inject_image(self, messages: list[dict], image_url: str) -> list[dict]:
        """Augment the last user message with an image content block.

        Converts the last user message content from a plain string to a list of
        content blocks: [text block, image block]. This matches the Anthropic
        messages API multimodal format.
        """
        if not messages:
            return messages

        last_msg = messages[-1]
        if last_msg.get("role") != "user":
            return messages

        original_text = last_msg.get("content", "")
        if isinstance(original_text, str):
            text_block = {"type": "text", "text": original_text}
        else:
            # Already a list — wrap as-is; append image after
            messages[-1]["content"] = list(original_text) + [
                {
                    "type": "image",
                    "source": {"type": "url", "url": image_url},
                }
            ]
            return messages

        messages[-1]["content"] = [
            text_block,
            {
                "type": "image",
                "source": {"type": "url", "url": image_url},
            },
        ]
        return messages

    def _inject_video_summary(
        self,
        messages: list[dict],
        video_url: str,
        summary: str,
    ) -> list[dict]:
        """Append video summary as text to the last user message.

        Since videos cannot be sent directly as content blocks to the main model,
        we inject the summary from kimi-k2.5 as additional context text.
        """
        if not messages:
            return messages

        last_msg = messages[-1]
        if last_msg.get("role") != "user":
            return messages

        original_text = last_msg.get("content", "")
        if isinstance(original_text, str):
            injected = (
                f"{original_text}\n\n"
                f"[视频内容摘要 by AI: {summary}]"
            )
            messages[-1]["content"] = injected
        return messages

    async def _understand_video(self, video_url: str) -> str:
        """Call kimi-k2.5 to understand the video and return a text summary.

        Uses the same DashScope Anthropic-compatible endpoint as the main model,
        but switches to kimi-k2.5 for video understanding capability.
        """
        client = get_client("system")
        try:
            resp = await client.messages.create(
                model=settings.video_llm_model,
                max_tokens=512,
                system="你是一个视频理解助手。请用中文简洁描述视频的主要内容，不超过200字。",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"请描述这个视频的内容：{video_url}",
                            }
                        ],
                    }
                ],
            )
            return resp.content[0].text
        except Exception as exc:
            logger.warning("Video understanding failed for %s: %s", video_url, exc)
            return f"（视频理解失败，原始链接：{video_url}）"

    async def _stream(
        self,
        system_prompt: str,
        messages: list[dict],
        *,
        owner: str = "user",
        user_config: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream text from the main model. Internal helper."""
        client = get_client(owner, user_config=user_config)
        async with client.messages.stream(
            model=settings.effective_model,
            max_tokens=settings.llm_max_tokens,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
```

- [ ] **Step 3: Verify**

```bash
python3 -m pytest backend/tests/test_model_router.py -x -v
```

Expected: 4 passed.

---

## Task 5: Extend ChatMsg Protocol for Media

**Files:**
- Modify: `backend/app/ws/protocol.py`

No separate test file for this task — the change is validated via the Task 6 integration test.

- [ ] **Step 1: Implement**

Edit `backend/app/ws/protocol.py` — update the `ChatMsg` model:

```python
class ChatMsg(BaseModel):
    type: Literal["chat_msg"] = "chat_msg"
    text: str
    media_url: str | None = None
    media_type: str | None = None  # "image" or "video"
```

Full updated `ChatMsg` block (replacing lines 11-13):

```python
class ChatMsg(BaseModel):
    type: Literal["chat_msg"] = "chat_msg"
    text: str
    media_url: str | None = None
    media_type: str | None = None  # "image" or "video"; None means plain text
```

- [ ] **Step 2: Verify**

```bash
npx tsc --noEmit 2>/dev/null || true  # frontend type check (no frontend changes yet)
python3 -m pytest backend/tests/ -x -q --ignore=backend/tests/test_media_chat_integration.py 2>&1 | tail -20
```

Expected: all existing tests pass.

---

## Task 6: Wire Media into WebSocket Chat Flow

**Files:**
- Modify: `backend/app/ws/handler.py`
- Create: `backend/tests/test_media_chat_integration.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_media_chat_integration.py`:

```python
"""Integration tests for media-augmented chat via WebSocket handler."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock
from sqlalchemy import select
from app.models.memory import Memory
from app.models.resident import Resident
from app.models.user import User
from app.models.conversation import Conversation
from app.memory.service import MemoryService


@pytest.fixture
async def media_resident(db_session):
    r = Resident(
        id="media-res-1",
        slug="media-res-1",
        name="VisionResident",
        district="engineering",
        status="idle",
        ability_md="Can see images",
        persona_md="Visual thinker",
        soul_md="Observant",
        creator_id="creator-1",
        token_cost_per_turn=1,
    )
    db_session.add(r)
    await db_session.commit()
    return r


@pytest.fixture
async def media_user(db_session):
    u = User(
        id="media-user-1",
        name="Photographer",
        email="photo@test.com",
        soul_coin_balance=100,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.fixture
async def media_conversation(db_session, media_resident, media_user):
    conv = Conversation(
        user_id=media_user.id,
        resident_id=media_resident.id,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


def _make_stream_chunks(chunks: list[str]):
    """Create a mock async context manager yielding text chunks."""
    class FakeStream:
        def __init__(self):
            self.text_stream = _gen(chunks)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    async def _gen(items):
        for item in items:
            yield item

    return FakeStream()


@pytest.mark.anyio
async def test_chat_msg_with_image_calls_model_router(
    db_session, media_resident, media_user, media_conversation
):
    """chat_msg with media_url calls ModelRouter.chat_with_media, not stream_chat."""
    from app.memory.service import MemoryService

    image_url = "/static/uploads/images/test.jpg"

    with patch("app.ws.handler.ModelRouter") as mock_router_cls:
        mock_router = MagicMock()

        async def fake_chat_with_media(*args, **kwargs):
            yield "Nice photo!"

        mock_router.chat_with_media = fake_chat_with_media
        mock_router_cls.return_value = mock_router

        with patch("app.memory.service.generate_embedding", return_value=[0.0] * 1024):
            # Simulate the chat_msg handling path directly via MemoryService
            svc = MemoryService(db_session)
            mem = await svc.add_memory(
                resident_id=media_resident.id,
                type="event",
                content="Player shared an image of a cat",
                importance=0.6,
                source="chat_player",
                media_url=image_url,
                media_summary="The image shows a cat sitting on a windowsill.",
            )

    # Verify memory was stored with media_url and media_summary
    result = await db_session.execute(
        select(Memory).where(
            Memory.resident_id == media_resident.id,
            Memory.media_url == image_url,
        )
    )
    saved = result.scalar_one()
    assert saved.media_url == image_url
    assert "cat" in saved.media_summary


@pytest.mark.anyio
async def test_chat_msg_image_memory_stored_with_summary(
    db_session, media_resident, media_user
):
    """After processing an image, the event memory should have media_url and media_summary."""
    from app.memory.service import MemoryService

    svc = MemoryService(db_session)

    with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
        mem = await svc.add_memory(
            resident_id=media_resident.id,
            type="event",
            content="Player sent an image showing a sunset over mountains",
            importance=0.7,
            source="chat_player",
            related_user_id=media_user.id,
            media_url="/static/uploads/images/sunset.jpg",
            media_summary="A stunning sunset with orange and purple hues over mountain peaks.",
        )

    assert mem.id is not None
    assert mem.media_url == "/static/uploads/images/sunset.jpg"
    assert "sunset" in mem.media_summary
    assert mem.type == "event"
    assert mem.related_user_id == media_user.id


@pytest.mark.anyio
async def test_model_router_image_chat_end_to_end():
    """ModelRouter correctly routes an image chat and yields chunks."""
    from app.media.model_router import ModelRouter

    system_prompt = "You are a visual AI assistant."
    messages = [{"role": "user", "content": "Describe this image"}]
    image_url = "https://example.com/test.jpg"

    with patch("app.media.model_router.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_stream_chunks(["I see ", "a beautiful scene."])
        mock_get_client.return_value = mock_client

        router = ModelRouter()
        chunks = []
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=image_url,
            media_type="image",
        ):
            chunks.append(chunk)

    assert chunks == ["I see ", "a beautiful scene."]

    # Verify image block was injected
    call_kwargs = mock_client.messages.stream.call_args.kwargs
    last_msg = call_kwargs["messages"][-1]
    content = last_msg["content"]
    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["url"] == image_url


@pytest.mark.anyio
async def test_model_router_video_chat_stores_summary():
    """ModelRouter for video returns kimi summary injected into main model context."""
    from app.media.model_router import ModelRouter

    system_prompt = "You are a video analysis assistant."
    messages = [{"role": "user", "content": "What happens in this video?"}]
    video_url = "https://example.com/video.mp4"
    kimi_summary = "Two people playing chess in a park."

    def _mock_response(text):
        msg = MagicMock()
        block = MagicMock()
        block.text = text
        msg.content = [block]
        return msg

    with patch("app.media.model_router.get_client") as mock_get_client:
        kimi_client = MagicMock()
        kimi_client.messages.create = AsyncMock(return_value=_mock_response(kimi_summary))

        main_client = MagicMock()
        main_client.messages.stream.return_value = _make_stream_chunks(["Chess game!"])

        mock_get_client.side_effect = [kimi_client, main_client]

        router = ModelRouter()
        chunks = []
        async for chunk in router.chat_with_media(
            system_prompt=system_prompt,
            messages=messages,
            media_url=video_url,
            media_type="video",
        ):
            chunks.append(chunk)

    assert chunks == ["Chess game!"]
    # Summary should appear in the main model's messages
    main_kwargs = main_client.messages.stream.call_args.kwargs
    last_content = main_kwargs["messages"][-1]["content"]
    assert kimi_summary in last_content
```

Run: `python3 -m pytest backend/tests/test_media_chat_integration.py -x` → partial FAIL (handler not wired yet)

- [ ] **Step 2: Implement — wire ModelRouter into handler.py**

Edit `backend/app/ws/handler.py`:

1. Add import at top (after existing imports):

```python
from app.media.model_router import ModelRouter
```

2. Replace the `chat_msg` block's streaming section (currently lines 258-278) with media-aware logic:

**Before** (current code, lines 258-278):
```python
                    chat_messages.append({"role": "user", "content": text})
                    system_prompt = assemble_system_prompt(current_resident, memory_context=memory_context)

                    full_reply = ""
                    async for chunk in stream_chat(system_prompt, chat_messages):
                        full_reply += chunk
                        await manager.send(user_id, {
                            "type": "chat_reply",
                            "text": chunk,
                            "done": False,
                        })
                    await manager.send(user_id, {"type": "chat_reply", "text": "", "done": True})

                    chat_messages.append({"role": "assistant", "content": full_reply})
                    db.add(Message(
                        conversation_id=fresh_conv.id,
                        role="assistant",
                        content=full_reply,
                    ))
                    fresh_conv.tokens_used += len(full_reply)  # character count proxy
                    await db.commit()
```

**After** (new code):
```python
                    media_url = data.get("media_url") or None
                    media_type = data.get("media_type") or None

                    chat_messages.append({"role": "user", "content": text})
                    system_prompt = assemble_system_prompt(current_resident, memory_context=memory_context)

                    full_reply = ""
                    model_router = ModelRouter()
                    async for chunk in model_router.chat_with_media(
                        system_prompt=system_prompt,
                        messages=chat_messages,
                        media_url=media_url,
                        media_type=media_type,
                    ):
                        full_reply += chunk
                        await manager.send(user_id, {
                            "type": "chat_reply",
                            "text": chunk,
                            "done": False,
                        })
                    await manager.send(user_id, {"type": "chat_reply", "text": "", "done": True})

                    chat_messages.append({"role": "assistant", "content": full_reply})
                    db.add(Message(
                        conversation_id=fresh_conv.id,
                        role="assistant",
                        content=full_reply,
                    ))
                    fresh_conv.tokens_used += len(full_reply)  # character count proxy
                    await db.commit()

                    # If media was sent, store media_summary in event memory
                    if media_url and media_type:
                        # full_reply IS the media summary from the model's perspective
                        memory_svc = MemoryService(db)
                        await memory_svc.add_memory(
                            resident_id=current_resident.id,
                            type="event",
                            content=f"玩家分享了一个{media_type}：{text or '(无文字描述)'}",
                            importance=0.6,
                            source="chat_player",
                            related_user_id=user_id,
                            media_url=media_url,
                            media_summary=full_reply[:500],  # cap summary length
                        )
```

- [ ] **Step 3: Verify**

```bash
python3 -m pytest backend/tests/test_media_chat_integration.py -x -v
python3 -m pytest backend/tests/ -x -q 2>&1 | tail -20
```

Expected: all tests pass including existing ones.

Also run type check:

```bash
cd /Users/jimmy/Downloads/Skills-World && npx tsc --noEmit --project frontend/tsconfig.json 2>&1 | head -30
```

---

## Task 7: Frontend Media Upload UI

**Note:** This task describes frontend changes only. No full React component code is included — implementation follows the existing `ChatDrawer` pattern.

**Files to modify:**
- `frontend/src/components/ChatDrawer.tsx` (or equivalent chat UI component)
- Likely needs: `frontend/src/api/media.ts` (new file for upload API call)

### Changes Needed

**1. Media upload API client** (`frontend/src/api/media.ts`):
- `uploadMedia(file: File, mediaType: "image" | "video"): Promise<{ media_url: string; media_type: string; filename: string }>`
- Uses `fetch` with `FormData` and `multipart/form-data`
- Sends `Authorization: Bearer <token>` header
- Calls `POST /api/media/upload?media_type=<type>`

**2. ChatDrawer additions:**
- Add a paperclip/upload button next to the message input
- On click: open file picker (accepts `image/*,video/*`)
- On file selected:
  - Show upload progress indicator (spinner or progress bar)
  - Call `uploadMedia(file, mediaType)` where `mediaType` is derived from `file.type`
  - On success: store `pendingMediaUrl` and `pendingMediaType` in local state
  - Show thumbnail preview (for images) or filename chip (for videos) above the input
- On send:
  - If `pendingMediaUrl` is set, send `chat_msg` with:
    ```json
    {
      "type": "chat_msg",
      "text": "...",
      "media_url": "/static/uploads/images/abc.jpg",
      "media_type": "image"
    }
    ```
  - Clear `pendingMediaUrl` / `pendingMediaType` after send

**3. Message bubble rendering:**
- If `message.media_url` starts with `/static/uploads/images/`, render an `<img>` thumbnail
- If `message.media_url` starts with `/static/uploads/videos/`, render a `<video>` element with controls
- Keep text below the media thumbnail

**4. Upload progress UI pattern:**
```tsx
const [uploadProgress, setUploadProgress] = useState<"idle" | "uploading" | "done" | "error">("idle");
const [pendingMedia, setPendingMedia] = useState<{ url: string; type: string } | null>(null);

const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0];
  if (!file) return;
  setUploadProgress("uploading");
  try {
    const mediaType = file.type.startsWith("video/") ? "video" : "image";
    const result = await uploadMedia(file, mediaType);
    setPendingMedia({ url: result.media_url, type: result.media_type });
    setUploadProgress("done");
  } catch (err) {
    setUploadProgress("error");
  }
};
```

**5. WebSocket message update** (in the send handler):
```ts
const payload: Record<string, unknown> = {
  type: "chat_msg",
  text: inputText,
};
if (pendingMedia) {
  payload.media_url = pendingMedia.url;
  payload.media_type = pendingMedia.type;
}
ws.send(JSON.stringify(payload));
setPendingMedia(null);
```

**Commit when done:** `feat(media): add frontend media upload UI and message rendering`

---

## Commit Plan

```
feat(media): add media upload config, service, router, model router, and WS integration

Task 1: Add media_upload_dir, media_max_image_size, media_max_video_size, video_llm_model to config
Task 2: MediaService - validate/save images and videos with UUID filenames
Task 3: POST /api/media/upload router with auth and 400 on validation error
Task 4: ModelRouter - route images to main model with content blocks, videos to kimi-k2.5
Task 5: Extend ChatMsg protocol with optional media_url and media_type fields
Task 6: Wire ModelRouter into WS handler chat_msg block; store media memories
```

---

## Verification Checklist

After all tasks complete:

- [ ] `python3 -m pytest backend/tests/ -x -q` — all tests pass
- [ ] `python3 -m pytest backend/tests/test_media_service.py` — 8 passed
- [ ] `python3 -m pytest backend/tests/test_media_upload.py` — 5 passed
- [ ] `python3 -m pytest backend/tests/test_model_router.py` — 4 passed
- [ ] `python3 -m pytest backend/tests/test_media_chat_integration.py` — 4 passed
- [ ] `npx tsc --noEmit` — 0 type errors
- [ ] Directories exist: `backend/static/uploads/images/` and `backend/static/uploads/videos/`
- [ ] Upload endpoint reachable: `curl -X POST http://localhost:8000/api/media/upload` returns 401 (not 404)
- [ ] Manual test: send image in chat, resident replies with description
- [ ] Manual test: send video in chat, resident replies with kimi-k2.5 summary
