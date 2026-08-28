"""The caravan schema stays on the repository's single linear Alembic chain."""
import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import sqlalchemy as sa


def test_caravan_migration_follows_embedding_queue_on_single_linear_chain():
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    revision = script.get_revision("060_add_caravan_lifecycle")
    assert revision.down_revision == "059_add_embedding_queue_index"
    assert len(script.get_heads()) == 1
    assert "060_add_caravan_lifecycle" in {
        rev.revision for rev in script.walk_revisions()
    }


def test_market_visitor_migration_extends_caravan_lifecycle_on_linear_chain():
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    revision = script.get_revision("061_add_caravan_market_visitors")

    assert revision.down_revision == "060_add_caravan_lifecycle"
    assert len(script.get_heads()) == 1
    assert "061_add_caravan_market_visitors" in {
        rev.revision for rev in script.walk_revisions()
    }


def test_agent_player_and_hosted_agent_migrations_extend_linear_chain():
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)

    agent_players = script.get_revision("062_add_agent_players")
    npc_turns = script.get_revision("063_agent_npc_chat_turns")
    quota_counters = script.get_revision("064_forge_quota_counters")
    ugc_privileges = script.get_revision("065_sanitize_ugc_privileges")
    hosted_agents = script.get_revision("066_hosted_agent_controllers")
    market_economy = script.get_revision("067_market_economy_loop")

    assert agent_players.down_revision == "061_add_caravan_market_visitors"
    assert npc_turns.down_revision == "062_add_agent_players"
    assert quota_counters.down_revision == "063_agent_npc_chat_turns"
    assert ugc_privileges.down_revision == "064_forge_quota_counters"
    assert hosted_agents.down_revision == "065_sanitize_ugc_privileges"
    assert market_economy.down_revision == "066_hosted_agent_controllers"
    assert script.get_heads() == ["069_living_loop_p0"]


def test_067_upgrade_and_downgrade_create_market_economy_schema():
    root = Path(__file__).resolve().parents[1]
    path = root / "alembic" / "versions" / "067_add_market_sessions_and_economy_bootstrap.py"
    spec = importlib.util.spec_from_file_location("migration_067", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    for name in ("users", "caravan_visits", "lab_tasks", "lab_artifacts"):
        sa.Table(name, metadata, sa.Column("id", sa.String, primary_key=True))
    sa.Table(
        "items",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("code", sa.String, unique=True),
        sa.Column("kind", sa.String),
        sa.Column("name", sa.String),
        sa.Column("description", sa.Text),
        sa.Column("icon", sa.String),
        sa.Column("price_sc", sa.Integer),
        sa.Column("payload_json", sa.JSON),
        sa.Column("stock", sa.Integer),
        sa.Column("active", sa.Boolean),
    )
    created = {
        "economy_bootstrap_batches",
        "economy_bootstrap_grants",
        "caravan_market_purchases",
        "lab_market_candidates",
    }
    receipt_codes = {
        "market_tea_chest",
        "market_trinket_display",
        "market_cloth_roll",
        "market_foreign_lantern",
    }
    with engine.begin() as connection:
        metadata.create_all(connection)
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        inspector = sa.inspect(connection)
        assert created <= set(inspector.get_table_names())
        rows = set(
            connection.execute(
                sa.text("SELECT code FROM items WHERE code LIKE 'market_%'")
            ).scalars()
        )
        assert rows == receipt_codes

        module.downgrade()
        assert created.isdisjoint(set(sa.inspect(connection).get_table_names()))
        assert connection.execute(
            sa.text("SELECT count(*) FROM items WHERE code LIKE 'market_%'")
        ).scalar_one() == 0
