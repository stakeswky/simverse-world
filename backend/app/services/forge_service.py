"""
DEPRECATED: This module is superseded by app/forge/pipeline.py.

New code should use app/forge/pipeline.py instead. This file is kept
intact because legacy endpoints (/forge/start, /forge/answer, /forge/status)
still route through these functions. Do NOT delete until those endpoints
are migrated.

----

Forge Service — orchestrates the 5-step guided conversation and LLM pipeline.

Flow:
  1. start_forge()     → create session, return Q2 (Q1 = name, already provided)
  2. submit_answer()   → store answer, advance step, return next question
  3. After Q5 answer   → trigger async LLM pipeline
  4. get_status()      → poll session state (collecting | generating | done | error)
"""

import asyncio
import json
import uuid
import re
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import get_client


def _extract_text(response) -> str:
    """Extract text from LLM response, skipping ThinkingBlocks (extended thinking)."""
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""
from app.llm.forge_prompts import (
    FORGE_QUESTIONS,
    ABILITY_SYSTEM_PROMPT, ABILITY_USER_TEMPLATE,
    PERSONA_SYSTEM_PROMPT, PERSONA_USER_TEMPLATE,
    SOUL_SYSTEM_PROMPT, SOUL_USER_TEMPLATE,
    SCORING_SYSTEM_PROMPT, SCORING_USER_TEMPLATE,
    DISTRICT_SYSTEM_PROMPT, DISTRICT_USER_TEMPLATE,
    QUICK_EXTRACT_SYSTEM_PROMPT, QUICK_EXTRACT_USER_TEMPLATE,
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
        from app.config import settings as _settings
        model = _settings.effective_model

        # Generate ability.md
        ability_resp = await client.messages.create(
            model=model, max_tokens=1500, system=ABILITY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": ABILITY_USER_TEMPLATE.format(
                name=name, ability_description=ability_desc,
                personality_description=personality_desc, material=material,
            )}],
        )
        session["ability_md"] = _extract_text(ability_resp)

        # Generate persona.md
        persona_resp = await client.messages.create(
            model=model, max_tokens=2000, system=PERSONA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": PERSONA_USER_TEMPLATE.format(
                name=name, personality_description=personality_desc,
                ability_description=ability_desc, soul_description=soul_desc,
                material=material,
            )}],
        )
        session["persona_md"] = _extract_text(persona_resp)

        # Generate soul.md
        soul_resp = await client.messages.create(
            model=model, max_tokens=1500, system=SOUL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": SOUL_USER_TEMPLATE.format(
                name=name, soul_description=soul_desc,
                personality_description=personality_desc,
                ability_description=ability_desc, material=material,
            )}],
        )
        session["soul_md"] = _extract_text(soul_resp)

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

        # Compute SBTI personality
        from app.services.sbti_service import compute_sbti, update_meta_with_sbti
        forge_meta: dict = {
            "role": _extract_role(session["ability_md"]),
            "impression": _extract_impression(session["persona_md"]),
            "origin": "forge",
        }
        sbti = await compute_sbti(name, session["ability_md"], session["persona_md"], session["soul_md"])
        if sbti:
            forge_meta = update_meta_with_sbti(forge_meta, sbti)

        # Create resident
        resident = Resident(
            slug=slug, name=name, district=district, status="idle", heat=0,
            model_tier="standard", token_cost_per_turn=1, creator_id=session["user_id"],
            ability_md=session["ability_md"], persona_md=session["persona_md"],
            soul_md=session["soul_md"],
            meta_json=forge_meta,
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


async def run_quick_pipeline(forge_id: str, db: AsyncSession) -> None:
    """
    Quick forge pipeline: single LLM call to extract all three layers from raw text.
    Much faster than the 5-step pipeline (1 call vs 5).
    """
    session = _sessions.get(forge_id)
    if not session:
        return

    try:
        name = session["name"]
        raw_text = session["answers"].get("2", "")

        from app.config import settings as _settings
        import anthropic
        import logging

        model = _settings.effective_model
        user_msg = QUICK_EXTRACT_USER_TEMPLATE.format(name=name, raw_text=raw_text)
        logging.warning(f"[FORGE] LLM call starting for '{name}' ({len(raw_text)} chars)")

        # Run LLM call in a subprocess to isolate from uvicorn's event loop
        # (uvicorn's anyio backend breaks TLS handshake for external HTTPS calls in background tasks)
        import subprocess, sys, tempfile

        req_payload = json.dumps({
            "api_key": _settings.effective_api_key,
            "base_url": _settings.llm_base_url or "https://api.anthropic.com",
            "model": model,
            "max_tokens": 4096,
            "system": QUICK_EXTRACT_SYSTEM_PROMPT,
            "user_msg": user_msg,
        })

        # Write request to temp file (avoid shell escaping issues with Chinese text)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(req_payload)
            req_file = f.name

        script = f"""
import json, asyncio, sys

async def call_llm():
    with open('{req_file}') as f:
        req = json.load(f)
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=req['api_key'], base_url=req['base_url'])
    resp = await client.messages.create(
        model=req['model'], max_tokens=req['max_tokens'],
        system=req['system'],
        messages=[{{"role": "user", "content": req['user_msg']}}],
    )
    # Extract text block
    for block in resp.content:
        if hasattr(block, 'text'):
            print(block.text)
            return
    print('')

asyncio.run(call_llm())
"""

        logging.warning(f"[FORGE] Launching subprocess for LLM call...")
        proc = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [sys.executable, '-c', script],
                capture_output=True, text=True, timeout=120,
                env={**__import__('os').environ, 'NO_PROXY': '*', 'HTTPS_PROXY': '', 'HTTP_PROXY': ''},
            ),
        )

        # Cleanup temp file
        import os
        os.unlink(req_file)

        if proc.returncode != 0:
            raise RuntimeError(f"LLM subprocess failed: {proc.stderr[:500]}")

        full_text = proc.stdout.strip()
        logging.warning(f"[FORGE] LLM returned {len(full_text)} chars")

        # Split on ===SPLIT===
        parts = [p.strip() for p in full_text.split("===SPLIT===")]
        session["ability_md"] = parts[0] if len(parts) > 0 else ""
        session["persona_md"] = parts[1] if len(parts) > 1 else ""
        session["soul_md"] = parts[2] if len(parts) > 2 else ""

        # If split didn't work well, try to parse by headers
        if len(parts) < 3 and "# 人格档案" in full_text:
            _parse_combined_output(session, full_text)

        # Score quality using fallback (skip LLM scoring for speed)
        session["star_rating"] = _compute_star_rating_fallback(
            session["ability_md"], session["persona_md"], session["soul_md"]
        )

        # Assign district using keyword matching (skip LLM for speed)
        combined = (session["ability_md"] + session["persona_md"]).lower()
        if any(kw in combined for kw in ["engineer", "backend", "frontend", "algorithm", "code", "编程", "架构", "开发"]):
            district = "engineering"
        elif any(kw in combined for kw in ["product", "design", "产品", "设计", "运营"]):
            district = "product"
        elif any(kw in combined for kw in ["teacher", "professor", "学者", "教授", "导师", "哲学"]):
            district = "academy"
        else:
            district = "free"
        session["district"] = district

        # Find tile, slug, create resident
        tile_x, tile_y = await _find_available_tile(db, district)
        slug = _generate_slug(name)
        existing = await db.execute(select(Resident).where(Resident.slug == slug))
        if existing.scalar_one_or_none():
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        # Compute SBTI personality
        from app.services.sbti_service import compute_sbti, update_meta_with_sbti
        quick_meta: dict = {
            "role": _extract_role(session["ability_md"]),
            "impression": _extract_impression(session["persona_md"]),
            "origin": "quick_forge",
        }
        sbti = await compute_sbti(name, session["ability_md"], session["persona_md"], session["soul_md"])
        if sbti:
            quick_meta = update_meta_with_sbti(quick_meta, sbti)

        resident = Resident(
            slug=slug, name=name, district=district, status="idle", heat=0,
            model_tier="standard", token_cost_per_turn=1, creator_id=session["user_id"],
            ability_md=session["ability_md"], persona_md=session["persona_md"],
            soul_md=session["soul_md"],
            meta_json=quick_meta,
            sprite_key=random.choice(SPRITE_KEYS),
            tile_x=tile_x, tile_y=tile_y, star_rating=session["star_rating"],
        )
        db.add(resident)
        await db.commit()
        await db.refresh(resident)
        session["resident_id"] = resident.id

        from app.services.coin_service import reward
        await reward(db, session["user_id"], 50, "forge_creation")

        session["status"] = "done"
        logging.info(f"Quick forge: '{name}' done — {district}, {session['star_rating']}★")

    except Exception as e:
        import logging, traceback
        logging.error(f"Quick forge error: {e}\n{traceback.format_exc()}")
        session["status"] = "error"
        session["error"] = str(e)


def _parse_combined_output(session: dict, text: str) -> None:
    """Fallback parser if ===SPLIT=== didn't work — split by top-level headers."""
    ability_start = text.find("# 能力")
    persona_start = text.find("# 人格")
    soul_start = text.find("# 灵魂")

    if ability_start >= 0 and persona_start > ability_start:
        session["ability_md"] = text[ability_start:persona_start].strip()
    if persona_start >= 0 and soul_start > persona_start:
        session["persona_md"] = text[persona_start:soul_start].strip()
    if soul_start >= 0:
        session["soul_md"] = text[soul_start:].strip()


async def _score_quality(client, model: str, name: str,
                         ability_md: str, persona_md: str, soul_md: str) -> int:
    try:
        resp = await client.messages.create(
            model=model, max_tokens=200, system=SCORING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": SCORING_USER_TEMPLATE.format(
                name=name, ability_md=ability_md, persona_md=persona_md, soul_md=soul_md,
            )}],
        )
        text = _extract_text(resp).strip()
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
        text = _extract_text(resp).strip()
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
