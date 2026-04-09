"""Sprites router: list templates and LLM-based persona matching."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.sprite_service import get_all_templates, match_sprite_by_persona

router = APIRouter(prefix="/sprites", tags=["sprites"])


class MatchRequest(BaseModel):
    persona_text: str


@router.get("/templates")
async def list_templates():
    """Return all 25 sprite templates with attributes."""
    return get_all_templates()


@router.post("/match")
async def match(body: MatchRequest):
    """Match sprite templates by persona text using LLM analysis."""
    if not body.persona_text.strip():
        raise HTTPException(status_code=400, detail="persona_text must not be empty")
    matched = await match_sprite_by_persona(body.persona_text)
    return matched
