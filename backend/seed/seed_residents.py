"""Seed 5 demo residents matching the verified demo/index.html NPCs."""
import asyncio
import json
from pathlib import Path
from app.agent.map_data import get_location_id_at
from app.database import engine, async_session, Base
from app.models.user import User
from app.models.resident import Resident
from app.services.forge_service import allocate_resident_location, normalize_location_id

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
_OVERRIDES_PATH = Path(__file__).with_name("generated") / "demo_resident_overrides.json"


def _load_overrides() -> dict[str, dict]:
    if not _OVERRIDES_PATH.exists():
        return {}
    return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))


def _apply_overrides(items: list[dict]) -> list[dict]:
    overrides = _load_overrides()
    merged_items = []
    for item in items:
        override = overrides.get(item["slug"], {})
        merged = {**item, **override}
        if item.get("meta_json") or override.get("meta_json"):
            merged["meta_json"] = {
                **(item.get("meta_json") or {}),
                **(override.get("meta_json") or {}),
            }
        merged_items.append(merged)
    return merged_items

SEED_DATA = [
    dict(slug="isabella", name="伊莎贝拉", district="north_path", status="idle", heat=15,
         sprite_key="伊莎贝拉", tile_x=70, tile_y=42, star_rating=2, creator_id=SYSTEM_USER_ID,
         token_cost_per_turn=1, ability_md="# 能力\n咖啡调制、客户服务",
         persona_md="# 人格\n热情开朗，喜欢和人聊天", soul_md="# 灵魂\n相信好咖啡能改变一天的心情",
         meta_json={"role": "咖啡店老板", "impression": "总是笑眯眯的"}),
    dict(slug="klaus", name="克劳斯", district="central_plaza", status="popular", heat=62,
         sprite_key="克劳斯", tile_x=58, tile_y=55, star_rating=3, creator_id=SYSTEM_USER_ID,
         token_cost_per_turn=1, ability_md="# 能力\n学术研究、论文写作",
         persona_md="# 人格\n严谨、话少、数据驱动", soul_md="# 灵魂\n追求真理，讨厌模糊的表述",
         meta_json={"role": "研究员", "impression": "总在思考什么"}),
    dict(slug="adam", name="亚当", district="central_plaza", status="sleeping", heat=0,
         sprite_key="亚当", tile_x=100, tile_y=52, star_rating=1, creator_id=SYSTEM_USER_ID,
         token_cost_per_turn=1, ability_md="# 能力\n药物学知识",
         persona_md="# 人格\n慵懒、随和", soul_md="# 灵魂\n享受当下",
         meta_json={"role": "药剂师", "impression": "经常打瞌睡"}),
    dict(slug="mei", name="梅", district="house_e", status="idle", heat=8,
         sprite_key="梅", tile_x=30, tile_y=65, star_rating=2, creator_id=SYSTEM_USER_ID,
         token_cost_per_turn=1, ability_md="# 能力\n学习能力强、好奇心旺盛",
         persona_md="# 人格\n活泼、爱提问", soul_md="# 灵魂\n相信学习是终身的事",
         meta_json={"role": "大学生", "impression": "总是充满好奇"}),
    dict(slug="tamara", name="塔玛拉", district="central_plaza", status="idle", heat=25,
         sprite_key="塔玛拉", tile_x=118, tile_y=38, star_rating=2, creator_id=SYSTEM_USER_ID,
         token_cost_per_turn=1, ability_md="# 能力\n创意写作、故事构思",
         persona_md="# 人格\n沉浸在自己的世界里", soul_md="# 灵魂\n文字是灵魂的出口",
         meta_json={"role": "作家", "impression": "总在记录灵感"}),
]

SEED_DATA = _apply_overrides(SEED_DATA)
SEED_DATA = [
    {
        **item,
        "district": normalize_location_id(
            get_location_id_at(item["tile_x"], item["tile_y"]) or item.get("district")
        ),
    }
    for item in SEED_DATA
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as db:
        # Create system user if not exists (for FK compliance)
        from sqlalchemy import select
        existing = await db.execute(select(User).where(User.id == SYSTEM_USER_ID))
        if not existing.scalar_one_or_none():
            system_user = User(
                id=SYSTEM_USER_ID,
                name="System",
                email="system@skills.world",
                soul_coin_balance=0,
            )
            db.add(system_user)
            await db.flush()

        # Seed residents (idempotent — skip if slug exists)
        for r_data in SEED_DATA:
            existing_r = await db.execute(select(Resident).where(Resident.slug == r_data["slug"]))
            if not existing_r.scalar_one_or_none():
                district, tile_x, tile_y, home_loc_id = await allocate_resident_location(
                    db,
                    requested_location_id=r_data.get("district"),
                    preferred_tile=(r_data["tile_x"], r_data["tile_y"]),
                    ability_text=r_data.get("ability_md", ""),
                    persona_text=r_data.get("persona_md", ""),
                    soul_text=r_data.get("soul_md", ""),
                )
                db.add(Resident(
                    **{
                        **r_data,
                        "district": district,
                        "tile_x": tile_x,
                        "tile_y": tile_y,
                        "home_location_id": r_data.get("home_location_id") or home_loc_id,
                    }
                ))

        await db.commit()
    print(f"Seeded {len(SEED_DATA)} residents")


if __name__ == "__main__":
    asyncio.run(seed())
