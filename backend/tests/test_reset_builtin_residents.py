"""Regression coverage for the production built-in-roster replacement."""

from sqlalchemy import select

from app.models.resident import Resident
from app.models.user import User
from seed.preset_characters import SYSTEM_USER_ID
from seed.reset_builtin_residents import find_targets, purge_residents


def _resident(*, slug: str, resident_type: str, creator_id: str) -> Resident:
    return Resident(
        slug=slug,
        name=slug,
        district="central_plaza",
        resident_type=resident_type,
        creator_id=creator_id,
    )


async def test_reset_targets_only_obsolete_builtin_npcs(db_session):
    player_owner = User(name="Player", email="player@example.com")
    db_session.add_all([
        User(
            id=SYSTEM_USER_ID,
            name="System",
            email="system@skills.world",
            soul_coin_balance=0,
        ),
        player_owner,
    ])
    await db_session.flush()

    legacy = _resident(
        slug="isabella", resident_type="npc", creator_id=SYSTEM_USER_ID
    )
    orphaned_system_npc = _resident(
        slug="retired-system-npc", resident_type="npc", creator_id=SYSTEM_USER_ID
    )
    player = _resident(
        slug="isabella-player", resident_type="player", creator_id=player_owner.id
    )
    user_npc = _resident(
        slug="user-created-npc", resident_type="npc", creator_id=player_owner.id
    )
    db_session.add_all([legacy, orphaned_system_npc, player, user_npc])
    await db_session.commit()

    targets = await find_targets(db_session)
    assert {resident.slug for resident in targets} == {
        "isabella",
        "retired-system-npc",
    }

    await purge_residents(db_session, targets)
    remaining = set((await db_session.scalars(select(Resident.slug))).all())
    assert remaining == {"isabella-player", "user-created-npc"}
