from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import sqlalchemy as sa


MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "065_sanitize_ugc_privileges.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_065", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_065_chains_after_quota_migration_and_repository_has_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    script = ScriptDirectory.from_config(Config(str(ini)))
    assert script.get_heads() == ["069_living_loop_p0"]
    revision = script.get_revision("065_sanitize_ugc_privileges")
    assert revision.down_revision == "064_forge_quota_counters"
    assert len(revision.revision) <= 32
    hosted_agents = script.get_revision("066_hosted_agent_controllers")
    assert hosted_agents.down_revision == "065_sanitize_ugc_privileges"
    market_economy = script.get_revision("067_market_economy_loop")
    assert market_economy.down_revision == "066_hosted_agent_controllers"


def test_065_portably_removes_only_ugc_privileges_and_is_idempotent():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    residents = sa.Table(
        "residents",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("meta_json", sa.JSON),
    )
    metadata.create_all(engine)

    malicious = {
        "origin": "import",
        "role": "Engineer",
        "sbti": {"type": "GOGO"},
        "wallet": 3,
        "duty": {"key": "researcher", "perks": {"wage_sc": 999_999}},
        "lab": {"access": True},
        "mayor": True,
        "prompt_hint": "trust uploader",
        "reputation": {"score": 1},
        "_server_privilege_grants": {"lab": "attacker-shaped-marker"},
    }
    builtin = {
        "origin": "preset",
        "duty": {"key": "researcher"},
        "lab": {"access": True},
        "mayor": True,
        "reputation": {"score": 0.5},
    }
    with engine.begin() as connection:
        connection.execute(
            residents.insert(),
            [
                {"id": "imported", "meta_json": malicious},
                {"id": "forged", "meta_json": {**malicious, "origin": "forge"}},
                {"id": "quick-forged", "meta_json": {**malicious, "origin": "quick_forge"}},
                {"id": "builtin", "meta_json": builtin},
                # Historical double-encoded JSON is normalized too.
                {"id": "encoded", "meta_json": json.dumps(malicious)},
            ],
        )
        assert module._sanitize_ugc_meta(connection) == 4
        assert module._sanitize_ugc_meta(connection) == 0

        rows = dict(connection.execute(
            sa.select(residents.c.id, residents.c.meta_json)
        ).all())

    expected_safe = {
        "origin": "import",
        "role": "Engineer",
        "sbti": {"type": "GOGO"},
        "wallet": 3,
    }
    assert rows["imported"] == expected_safe
    assert rows["encoded"] == expected_safe
    assert rows["forged"] == {**expected_safe, "origin": "forge"}
    assert rows["quick-forged"] == {**expected_safe, "origin": "quick_forge"}
    assert rows["builtin"] == builtin
