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
