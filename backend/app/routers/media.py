"""Media upload router: POST /api/media/upload."""
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import verify_token
from app.media.service import MediaService, MediaValidationError

router = APIRouter(prefix="/api/media", tags=["media"])


def _require_user_id(request: Request) -> str:
    """Extract and verify user_id from Authorization Bearer token. Raises 401 if invalid."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user_id = verify_token(auth.removeprefix("Bearer "))
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_id


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
    _require_user_id(request)

    svc = MediaService()
    try:
        result = await svc.save_upload(file, media_type=media_type)
    except MediaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return UploadResponse(**result)
