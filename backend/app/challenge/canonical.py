from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.challenge.models import ChallengeWorld

if TYPE_CHECKING:
    from app.challenge.models import WorldDiff


def canonical_json(value: BaseModel | dict[str, object] | list[object]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def world_hash(world: ChallengeWorld) -> str:
    material = (
        "simverse-challenge-world-v1\n"
        f"{world.scenario_id}\n"
        f"{world.fixture_version}\n"
        f"{canonical_json(world)}"
    )
    return f"sha256:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def diff_hash(diff: WorldDiff) -> str:
    material = (
        "simverse-challenge-diff-v1\n"
        f"{diff.scenario_id}\n"
        f"{diff.session_generation}\n"
        f"{diff.based_on_world_version}\n"
        f"{canonical_json(diff)}"
    )
    return f"sha256:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"
