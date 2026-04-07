"""
Forge Service — orchestrates the 5-step guided conversation and LLM pipeline.

Flow:
  1. start_forge()     → create session, return Q2 (Q1 = name, already provided)
  2. submit_answer()   → store answer, advance step, return next question
  3. After Q5 answer   → trigger async LLM pipeline
  4. get_status()      → poll session state (collecting | generating | done | error)
"""

import json
import uuid
import re
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import get_client
from app.llm.forge_prompts import (
    FORGE_QUESTIONS,
    ABILITY_SYSTEM_PROMPT, ABILITY_USER_TEMPLATE,
    PERSONA_SYSTEM_PROMPT, PERSONA_USER_TEMPLATE,
    SOUL_SYSTEM_PROMPT, SOUL_USER_TEMPLATE,
    SCORING_SYSTEM_PROMPT, SCORING_USER_TEMPLATE,
    DISTRICT_SYSTEM_PROMPT, DISTRICT_USER_TEMPLATE,
)
from app.models.resident import Resident

# In-memory sessions (MVP — replace with Redis for production)
_sessions: dict[str, dict[str, Any]] = {}

DISTRICT_TILE_SLOTS: dict[str, list[tuple[int, int]]] = {
    "engineering": [(58, 55), (60, 55), (62, 55), (56, 57), (58, 57), (60, 57),
                    (62, 57), (64, 57), (56, 59), (58, 59), (60, 59), (62, 59),
                    (64, 59), (56, 61), (58, 61), (60, 61), (62, 61), (64, 61),
                    (56, 63), (58, 63)],
    "product":     [(35, 40), (37, 40), (39, 40), (35, 42), (37, 42), (39, 42),
                    (35, 44), (37, 44), (39, 44), (35, 46), (37, 46), (39, 46),
                    (35, 48), (37, 48), (39, 48), (35, 50), (37, 50), (39, 50),
                    (35, 52), (37, 52)],
    "academy":     [(30, 65), (32, 65), (34, 65), (30, 67), (32, 67), (34, 67),
                    (30, 69), (32, 69), (34, 69), (30, 71), (32, 71), (34, 71),
                    (30, 73), (32, 73), (34, 73), (30, 75), (32, 75), (34, 75),
                    (30, 77), (32, 77)],
    "free":        [(100, 38), (102, 38), (104, 38), (106, 38), (108, 38),
                    (100, 40), (102, 40), (104, 40), (106, 40), (108, 40),
                    (100, 42), (102, 42), (104, 42), (106, 42), (108, 42),
                    (100, 44), (102, 44), (104, 44), (106, 44), (108, 44)],
}

SPRITE_KEYS = [
    "伊莎贝拉", "克劳斯", "亚当", "梅", "塔玛拉",
    "亚瑟", "卡洛斯", "弗朗西斯科", "海莉", "拉托亚",
    "詹妮弗", "约翰", "玛丽亚", "沃尔夫冈", "汤姆",
    "山本百合子", "山姆", "乔治", "简", "埃迪",
]


def start_forge(user_id: str, name: str) -> dict[str, Any]:
    forge_id = str(uuid.uuid4())
    _sessions[forge_id] = {
        "forge_id": forge_id,
        "user_id": user_id,
        "status": "collecting",
        "step": 1,
        "name": name,
        "answers": {"1": name},
        "ability_md": "",
        "persona_md": "",
        "soul_md": "",
        "star_rating": 0,
        "district": "",
        "resident_id": None,
        "error": None,
    }
    return {
        "forge_id": forge_id,
        "step": 1,
        "question": FORGE_QUESTIONS[2],
    }


def submit_answer(forge_id: str, answer: str) -> dict[str, Any]:
    session = _sessions.get(forge_id)
    if not session:
        raise ValueError("Forge session not found")
    if session["status"] != "collecting":
        raise ValueError(f"Session is in '{session['status']}' state")

    current_step = session["step"] + 1
    session["answers"][str(current_step)] = answer
    session["step"] = current_step

    if current_step >= 5:
        session["status"] = "generating"
        return {
            "forge_id": forge_id,
            "step": current_step,
            "next_step": None,
            "question": None,
            "ability_md": None,
            "persona_md": None,
            "soul_md": None,
        }

    next_q = current_step + 1
    return {
        "forge_id": forge_id,
        "step": current_step,
        "next_step": next_q,
        "question": FORGE_QUESTIONS[next_q],
        "ability_md": None,
        "persona_md": None,
        "soul_md": None,
    }


def get_status(forge_id: str) -> dict[str, Any]:
    session = _sessions.get(forge_id)
    if not session:
        raise ValueError("Forge session not found")
    return {
        "forge_id": session["forge_id"],
        "status": session["status"],
        "step": session["step"],
        "name": session["name"],
        "answers": session["answers"],
        "ability_md": session["ability_md"],
        "persona_md": session["persona_md"],
        "soul_md": session["soul_md"],
        "star_rating": session["star_rating"],
        "district": session["district"],
        "resident_id": session["resident_id"],
        "error": session["error"],
    }


async def run_generation_pipeline(forge_id: str, db: AsyncSession) -> None:
    session = _sessions.get(forge_id)
    if not session:
        return

    try:
        name = session["name"]
        answers = session["answers"]
        ability_desc = answers.get("2", "")
        personality_desc = answers.get("3", "")
        soul_desc = answers.get("4", "")
        material = answers.get("5", "")
        if material.strip().lower() in ("跳过", "skip", "无", "没有", ""):
            material = "无补充材料"

        client = get_client()
        model = "claude-haiku-4-5-20251001"  # use haiku for cost efficiency

        # Generate ability.md
        ability_resp = await client.messages.create(
            model=model, max_tokens=1500, system=ABILITY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": ABILITY_USER_TEMPLATE.format(
                name=name, ability_description=ability_desc,
                personality_description=personality_desc, material=material,
            )}],
        )
        session["ability_md"] = ability_resp.content[0].text

        # Generate persona.md
        persona_resp = await client.messages.create(
            model=model, max_tokens=2000, system=PERSONA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": PERSONA_USER_TEMPLATE.format(
                name=name, personality_description=personality_desc,
                ability_description=ability_desc, soul_description=soul_desc,
                material=material,
            )}],
        )
        session["persona_md"] = persona_resp.content[0].text

        # Generate soul.md
        soul_resp = await client.messages.create(
            model=model, max_tokens=1500, system=SOUL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": SOUL_USER_TEMPLATE.format(
                name=name, soul_description=soul_desc,
                personality_description=personality_desc,
                ability_description=ability_desc, material=material,
            )}],
        )
        session["soul_md"] = soul_resp.content[0].text

        # Score quality
        star_rating = await _score_quality(
            client, model, name,
            session["ability_md"], session["persona_md"], session["soul_md"],
        )
        session["star_rating"] = star_rating

        # Assign district
        district = await _assign_district(client, model, name, ability_desc, personality_desc)
        session["district"] = district

        # Find tile
        tile_x, tile_y = await _find_available_tile(db, district)

        # Generate slug
        slug = _generate_slug(name)
        existing = await db.execute(select(Resident).where(Resident.slug == slug))
        if existing.scalar_one_or_none():
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        # Create resident
        resident = Resident(
            slug=slug, name=name, district=district, status="idle", heat=0,
            model_tier="standard", token_cost_per_turn=1, creator_id=session["user_id"],
            ability_md=session["ability_md"], persona_md=session["persona_md"],
            soul_md=session["soul_md"],
            meta_json={
                "role": _extract_role(session["ability_md"]),
                "impression": _extract_impression(session["persona_md"]),
                "origin": "forge",
            },
            sprite_key=random.choice(SPRITE_KEYS),
            tile_x=tile_x, tile_y=tile_y, star_rating=star_rating,
        )
        db.add(resident)
        await db.commit()
        await db.refresh(resident)
        session["resident_id"] = resident.id

        # Reward creator
        from app.services.coin_service import reward
        await reward(db, session["user_id"], 50, "forge_creation")

        session["status"] = "done"

    except Exception as e:
        session["status"] = "error"
        session["error"] = str(e)


async def _score_quality(client, model: str, name: str,
                         ability_md: str, persona_md: str, soul_md: str) -> int:
    try:
        resp = await client.messages.create(
            model=model, max_tokens=200, system=SCORING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": SCORING_USER_TEMPLATE.format(
                name=name, ability_md=ability_md, persona_md=persona_md, soul_md=soul_md,
            )}],
        )
        text = resp.content[0].text.strip()
        match = re.search(r'\{[^}]+\}', text)
        if match:
            data = json.loads(match.group())
            return max(1, min(3, int(data.get("star_rating", 1))))
    except Exception:
        pass
    return _compute_star_rating_fallback(ability_md, persona_md, soul_md)


def _compute_star_rating_fallback(ability_md: str, persona_md: str, soul_md: str) -> int:
    total_len = len(ability_md) + len(persona_md) + len(soul_md)
    sections = 0
    for md in [ability_md, persona_md, soul_md]:
        headers = re.findall(r'^##\s+.+', md, re.MULTILINE)
        for h in headers:
            idx = md.index(h)
            after = md[idx + len(h):idx + len(h) + 200]
            if after.strip() and "暂无" not in after[:100] and "待补充" not in after[:100]:
                sections += 1
    empty_markers = sum(md.count("暂无") + md.count("待补充") for md in [ability_md, persona_md, soul_md])

    if sections < 3 or empty_markers > 5 or (total_len < 300 and sections < 2):
        return 1
    elif sections >= 10 and empty_markers <= 1:
        return 3
    else:
        return 2


async def _assign_district(client, model: str, name: str,
                            ability_desc: str, personality_desc: str) -> str:
    try:
        resp = await client.messages.create(
            model=model, max_tokens=100, system=DISTRICT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": DISTRICT_USER_TEMPLATE.format(
                name=name, ability_description=ability_desc,
                personality_description=personality_desc,
            )}],
        )
        text = resp.content[0].text.strip()
        match = re.search(r'\{[^}]+\}', text)
        if match:
            data = json.loads(match.group())
            district = data.get("district", "free")
            if district in DISTRICT_TILE_SLOTS:
                return district
    except Exception:
        pass
    return "free"


async def _find_available_tile(db: AsyncSession, district: str) -> tuple[int, int]:
    slots = DISTRICT_TILE_SLOTS.get(district, DISTRICT_TILE_SLOTS["free"])
    result = await db.execute(
        select(Resident.tile_x, Resident.tile_y).where(Resident.district == district)
    )
    occupied = {(row.tile_x, row.tile_y) for row in result.all()}
    for x, y in slots:
        if (x, y) not in occupied:
            return x, y
    base_x, base_y = slots[-1]
    return base_x + random.randint(1, 5) * 2, base_y + random.randint(1, 5) * 2


def _generate_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    if not slug:
        slug = f"resident-{uuid.uuid4().hex[:8]}"
    return slug


def _extract_role(ability_md: str) -> str:
    match = re.search(r'#\s*能力概览\s*\n+(.+)', ability_md)
    if match:
        return match.group(1).strip()[:50]
    for line in ability_md.split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            return line[:50]
    return "居民"


def _extract_impression(persona_md: str) -> str:
    match = re.search(r'Layer\s*0[^\n]*\n+([\s\S]*?)(?=\n##|\Z)', persona_md)
    if match:
        text = match.group(1).strip()
        bullet = re.search(r'-\s*\*\*(.+?)\*\*', text)
        if bullet:
            return bullet.group(1).strip()[:50]
        lines = [l.strip() for l in text.split('\n') if l.strip() and not l.strip().startswith('#')]
        if lines:
            return lines[0][:50]
    return "新入住的居民"
