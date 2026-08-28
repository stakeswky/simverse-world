"""Living Loop P0 stays on the portable, reversible Alembic head."""

from __future__ import annotations

from datetime import UTC, date, datetime
import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "069_living_loop_p0.py"
REVISION = "069_living_loop_p0"
PREVIOUS_REVISION = "068_fix_theater_bounds"
P0_TABLES = {"living_loop_days", "product_events"}


def _load_migration():
    assert MIGRATION.is_file(), "Living Loop P0 must ship its 069 migration"
    spec = importlib.util.spec_from_file_location("migration_069", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _columns_by_name(
    inspector: sa.Inspector, table_name: str
) -> dict[str, dict]:
    return {
        str(column["name"]): column
        for column in inspector.get_columns(table_name)
    }


def _indexed_column_sets(
    inspector: sa.Inspector, table_name: str
) -> set[tuple[str, ...]]:
    return {
        tuple(index["column_names"])
        for index in inspector.get_indexes(table_name)
    }


def _unique_column_sets(
    inspector: sa.Inspector, table_name: str
) -> set[tuple[str, ...]]:
    constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }
    unique_indexes = {
        tuple(index["column_names"])
        for index in inspector.get_indexes(table_name)
        if index.get("unique")
    }
    return constraints | unique_indexes


def _assert_living_loop_schema(connection: sa.Connection) -> None:
    inspector = sa.inspect(connection)
    assert P0_TABLES <= set(inspector.get_table_names())

    assert _column_names(inspector, "living_loop_days") == {
        "id",
        "user_id",
        "experiment_key",
        "day_key",
        "scenario_key",
        "scenario_version",
        "state",
        "scenario_snapshot_json",
        "choice_key",
        "choice_idempotency_key",
        "immediate_result_json",
        "delayed_result_json",
        "first_viewed_at",
        "choice_confirmed_at",
        "result_available_at",
        "result_settled_at",
        "result_viewed_at",
        "created_at",
        "updated_at",
    }
    assert _column_names(inspector, "product_events") == {
        "id",
        "event_id",
        "user_id",
        "session_id",
        "event_name",
        "properties_json",
        "occurred_at",
        "client_occurred_at",
        "created_at",
    }

    day_columns = _columns_by_name(inspector, "living_loop_days")
    event_columns = _columns_by_name(inspector, "product_events")
    assert isinstance(day_columns["id"]["type"], sa.String)
    assert day_columns["id"]["type"].length == 36
    assert isinstance(day_columns["day_key"]["type"], sa.Date)
    assert isinstance(day_columns["scenario_version"]["type"], sa.Integer)
    assert isinstance(day_columns["choice_idempotency_key"]["type"], sa.String)
    assert day_columns["choice_idempotency_key"]["type"].length == 36
    for column_name in (
        "scenario_snapshot_json",
        "immediate_result_json",
        "delayed_result_json",
    ):
        assert isinstance(day_columns[column_name]["type"], sa.JSON)
    for column_name in (
        "first_viewed_at",
        "choice_confirmed_at",
        "result_available_at",
        "result_settled_at",
        "result_viewed_at",
        "created_at",
        "updated_at",
    ):
        assert isinstance(day_columns[column_name]["type"], sa.DateTime)

    assert isinstance(event_columns["id"]["type"], sa.String)
    assert event_columns["id"]["type"].length == 36
    assert isinstance(event_columns["event_id"]["type"], sa.String)
    assert event_columns["event_id"]["type"].length == 36
    assert isinstance(event_columns["properties_json"]["type"], sa.JSON)
    for column_name in ("occurred_at", "client_occurred_at", "created_at"):
        assert isinstance(event_columns[column_name]["type"], sa.DateTime)

    assert inspector.get_pk_constraint("living_loop_days")["constrained_columns"] == [
        "id"
    ]
    assert inspector.get_pk_constraint("product_events")["constrained_columns"] == [
        "id"
    ]
    assert (
        "user_id",
        "experiment_key",
        "day_key",
    ) in _unique_column_sets(inspector, "living_loop_days")
    assert ("choice_idempotency_key",) in _unique_column_sets(
        inspector, "living_loop_days"
    )
    assert ("event_id",) in _unique_column_sets(inspector, "product_events")

    assert ("user_id",) in _indexed_column_sets(inspector, "living_loop_days")
    product_indexes = _indexed_column_sets(inspector, "product_events")
    assert {("user_id",), ("session_id",), ("event_name",)} <= product_indexes

    state_checks = [
        str(constraint.get("sqltext") or "").lower()
        for constraint in inspector.get_check_constraints("living_loop_days")
        if "state" in str(constraint.get("sqltext") or "").lower()
    ]
    assert len(state_checks) == 1
    for state in ("pending", "chosen", "result_ready", "result_viewed"):
        assert state in state_checks[0]


def _exercise_constraints(connection: sa.Connection) -> None:
    users = sa.Table("users", sa.MetaData(), autoload_with=connection)
    days = sa.Table("living_loop_days", sa.MetaData(), autoload_with=connection)
    events = sa.Table("product_events", sa.MetaData(), autoload_with=connection)
    connection.execute(
        users.insert(),
        [{"id": "user-1"}, {"id": "user-2"}, {"id": "user-3"}],
    )

    now = datetime(2026, 8, 28, 12, tzinfo=UTC)
    valid_day = {
        "id": "day-1",
        "user_id": "user-1",
        "experiment_key": "living_loop_p0",
        "day_key": date(2026, 8, 28),
        "scenario_key": "market_day",
        "scenario_version": 1,
        "state": "pending",
        "scenario_snapshot_json": {"key": "market_day", "version": 1},
        "immediate_result_json": {},
        "delayed_result_json": {},
        "created_at": now,
        "updated_at": now,
    }
    connection.execute(days.insert().values(**valid_day))

    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(
            days.insert().values(
                **{
                    **valid_day,
                    "id": "day-duplicate",
                    "scenario_key": "another_scenario",
                }
            )
        )
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(
            days.insert().values(
                **{
                    **valid_day,
                    "id": "day-bad-state",
                    "user_id": "user-2",
                    "state": "invented",
                }
            )
        )

    valid_event = {
        "id": "row-1",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "user_id": "user-1",
        "session_id": "00000000-0000-4000-8000-000000000010",
        "event_name": "living_loop_today_viewed",
        "properties_json": {"source": "today"},
        "occurred_at": now,
        "created_at": now,
    }
    connection.execute(events.insert().values(**valid_event))
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(
            events.insert().values(
                **{
                    **valid_event,
                    "id": "row-duplicate",
                    "user_id": "user-3",
                }
            )
        )


def test_069_is_the_single_head_directly_after_068() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))

    assert script.get_heads() == [REVISION]
    revision = script.get_revision(REVISION)
    assert revision.down_revision == PREVIOUS_REVISION
    assert len(revision.revision) <= 32


def test_069_sqlite_upgrade_downgrade_upgrade_preserves_only_parent_schema() -> None:
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.String(), primary_key=True))

    with engine.begin() as connection:
        metadata.create_all(connection)
        module.op = Operations(MigrationContext.configure(connection))

        module.upgrade()
        _assert_living_loop_schema(connection)
        _exercise_constraints(connection)

        module.downgrade()
        after_downgrade = sa.inspect(connection)
        assert P0_TABLES.isdisjoint(after_downgrade.get_table_names())
        assert "users" in after_downgrade.get_table_names()

        module.upgrade()
        _assert_living_loop_schema(connection)

    engine.dispose()
