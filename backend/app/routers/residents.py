from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.resident import ResidentListItem, ResidentDetail
from app.services.resident_service import list_residents, get_resident_by_slug

router = APIRouter(prefix="/residents", tags=["residents"])


@router.get("", response_model=list[ResidentListItem])
async def list_all(db: AsyncSession = Depends(get_db)):
    residents = await list_residents(db)
    return [ResidentListItem.model_validate(r, from_attributes=True) for r in residents]


@router.get("/{slug}", response_model=ResidentDetail)
async def get_one(slug: str, db: AsyncSession = Depends(get_db)):
    r = await get_resident_by_slug(db, slug)
    if not r:
        raise HTTPException(status_code=404, detail="Resident not found")
    return ResidentDetail.model_validate(r, from_attributes=True)
