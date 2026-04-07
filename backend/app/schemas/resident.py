from pydantic import BaseModel


class ResidentListItem(BaseModel):
    id: str
    slug: str
    name: str
    district: str
    status: str
    heat: int
    sprite_key: str
    tile_x: int
    tile_y: int
    star_rating: int
    token_cost_per_turn: int
    meta_json: dict | None

    model_config = {"from_attributes": True}


class ResidentDetail(ResidentListItem):
    ability_md: str
    persona_md: str
    soul_md: str
    total_conversations: int
    avg_rating: float
    creator_id: str
