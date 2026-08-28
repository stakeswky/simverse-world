"""Disposable real-PostgreSQL acceptance gate for Living Loop P0.

The ordinary Living Loop migration and concurrency tests intentionally use
SQLite.  This opt-in test proves the PostgreSQL-only contract against a random
database created inside the GitHub Actions PostgreSQL service.  It refuses to
run anywhere except an explicitly disposable loopback Actions environment.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.models.living_loop_day import LivingLoopDay
from app.models.product_event import ProductEvent
from app.models.resident import Resident
from app.models.user import User
from app.services.living_loop_service import LivingLoopError, choose, get_today
from app.services.settings_service import delete_account


pytestmark = [pytest.mark.lab_postgres, pytest.mark.anyio]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
TRUE = {"1", "true", "yes", "on"}
DATABASE_PREFIX = "simverse_living_loop_ci_"

DAY_COLUMNS = {
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
EVENT_COLUMNS = {
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
JSON_COLUMNS = {
    ("living_loop_days", "scenario_snapshot_json"),
    ("living_loop_days", "immediate_result_json"),
    ("living_loop_days", "delayed_result_json"),
    ("product_events", "properties_json"),
}
TIMESTAMPTZ_COLUMNS = {
    ("living_loop_days", "first_viewed_at"),
    ("living_loop_days", "choice_confirmed_at"),
    ("living_loop_days", "result_available_at"),
    ("living_loop_days", "result_settled_at"),
    ("living_loop_days", "result_viewed_at"),
    ("living_loop_days", "created_at"),
    ("living_loop_days", "updated_at"),
    ("product_events", "occurred_at"),
    ("product_events", "client_occurred_at"),
    ("product_events", "created_at"),
}
DAY_CHECKS = {
    "ck_living_loop_days_experiment",
    "ck_living_loop_days_scenario_version",
    "ck_living_loop_days_state",
    "ck_living_loop_days_choice",
    "ck_living_loop_days_choice_idempotency",
}
DAY_UNIQUES = {
    "uq_living_loop_day_user_experiment_day": (
        "user_id",
        "experiment_key",
        "day_key",
    ),
    "uq_living_loop_days_choice_idempotency_key": ("choice_idempotency_key",),
}
EVENT_CHECKS = {"ck_product_events_name"}
EVENT_UNIQUES = {"uq_product_events_event_id": ("event_id",)}
DAY_INDEXES = {"ix_living_loop_days_user_id": ("user_id",)}
EVENT_INDEXES = {
    "ix_product_events_user_id": ("user_id",),
    "ix_product_events_session_id": ("session_id",),
    "ix_product_events_event_name": ("event_name",),
    "ix_product_events_occurred_at": ("occurred_at",),
    "ix_product_events_created_at": ("created_at",),
}


def _required_database_url() -> str:
    if os.environ.get("LIVING_LOOP_POSTGRES_REQUIRED", "").lower() not in TRUE:
        pytest.skip("real PostgreSQL Living Loop acceptance was not requested")
    if os.environ.get("GITHUB_ACTIONS", "").lower() not in TRUE:
        pytest.fail("Living Loop PostgreSQL acceptance is restricted to GitHub Actions")
    if os.environ.get("LIVING_LOOP_PG_ACCEPTANCE_DISPOSABLE", "").lower() not in TRUE:
        pytest.fail("disposable PostgreSQL acceptance guard is not enabled")

    database_url = os.environ.get("LIVING_LOOP_TEST_DATABASE_URL", "")
    if not database_url:
        pytest.fail("LIVING_LOOP_TEST_DATABASE_URL is required")
    parsed = make_url(database_url)
    if parsed.drivername != "postgresql+asyncpg":
        pytest.fail("Living Loop acceptance requires postgresql+asyncpg")
    if parsed.host not in {"127.0.0.1", "localhost"}:
        pytest.fail("Living Loop acceptance database must be loopback-only")
    if parsed.username != "postgres":
        pytest.fail("Living Loop acceptance requires the disposable CI superuser")
    return database_url


def _alembic(env: dict[str, str], *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=600,
    )
    if result.returncode:
        pytest.fail(
            f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"
        )


@asynccontextmanager
async def _fresh_database():
    source_url = make_url(_required_database_url())
    database_name = f"{DATABASE_PREFIX}{uuid4().hex}"
    if re.fullmatch(r"simverse_living_loop_ci_[0-9a-f]{32}", database_name) is None:
        pytest.fail("generated database name failed the destructive-operation guard")

    control_url = source_url.set(database="postgres").render_as_string(
        hide_password=False
    )
    target_url = source_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    control = create_async_engine(control_url, isolation_level="AUTOCOMMIT")
    created = False
    try:
        async with control.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
            await connection.execute(
                text(
                    f'ALTER DATABASE "{database_name}" SET '
                    "simverse.living_loop_acceptance_disposable = 'on'"
                )
            )
        created = True

        probe = create_async_engine(target_url)
        try:
            async with probe.connect() as connection:
                database, disposable = (
                    await connection.execute(
                        text(
                            "SELECT current_database(), "
                            "current_setting("
                            "'simverse.living_loop_acceptance_disposable', true)"
                        )
                    )
                ).one()
            assert (database, disposable) == (database_name, "on")
        finally:
            await probe.dispose()
        yield target_url
    finally:
        if created:
            if not database_name.startswith(DATABASE_PREFIX):
                pytest.fail("refusing to drop an unguarded database name")
            async with control.connect() as connection:
                await connection.execute(
                    text(f'DROP DATABASE "{database_name}" WITH (FORCE)')
                )
        await control.dispose()


async def _revision(engine: AsyncEngine) -> str:
    async with engine.connect() as connection:
        return str(
            (
                await connection.execute(
                    text("SELECT version_num FROM alembic_version")
                )
            ).scalar_one()
        )


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))


async def _assert_schema(engine: AsyncEngine) -> None:
    def inspect_contract(sync_connection):
        inspector = inspect(sync_connection)
        result = {}
        for table in ("living_loop_days", "product_events"):
            result[table] = {
                "columns": {column["name"] for column in inspector.get_columns(table)},
                "checks": {
                    constraint["name"]: constraint["sqltext"]
                    for constraint in inspector.get_check_constraints(table)
                },
                "uniques": {
                    constraint["name"]: tuple(constraint["column_names"])
                    for constraint in inspector.get_unique_constraints(table)
                },
                "indexes": {
                    index["name"]: tuple(index["column_names"])
                    for index in inspector.get_indexes(table)
                    if not index.get("unique")
                    and not index.get("duplicates_constraint")
                },
                "foreign_keys": inspector.get_foreign_keys(table),
                "primary_key": inspector.get_pk_constraint(table),
            }
        return result

    async with engine.connect() as connection:
        contract = await connection.run_sync(inspect_contract)
        type_rows = (
            await connection.execute(
                text(
                    "SELECT table_name, column_name, data_type "
                    "FROM information_schema.columns "
                    "WHERE table_schema='public' "
                    "AND table_name IN ('living_loop_days','product_events')"
                )
            )
        ).all()

    assert contract["living_loop_days"]["columns"] == DAY_COLUMNS
    assert contract["product_events"]["columns"] == EVENT_COLUMNS
    assert set(contract["living_loop_days"]["checks"]) == DAY_CHECKS
    assert set(contract["product_events"]["checks"]) == EVENT_CHECKS
    assert contract["living_loop_days"]["uniques"] == DAY_UNIQUES
    assert contract["product_events"]["uniques"] == EVENT_UNIQUES
    assert contract["living_loop_days"]["indexes"] == DAY_INDEXES
    assert contract["product_events"]["indexes"] == EVENT_INDEXES
    check_tokens = {
        "ck_living_loop_days_experiment": {"experiment_key", "living_loop_p0"},
        "ck_living_loop_days_scenario_version": {"scenario_version", "1"},
        "ck_living_loop_days_state": {
            "state",
            "pending",
            "chosen",
            "result_ready",
            "result_viewed",
        },
        "ck_living_loop_days_choice": {
            "choice_key",
            "public_support",
            "private_mediation",
            "collect_evidence",
        },
        "ck_living_loop_days_choice_idempotency": {
            "choice_idempotency_key",
            "choice_key",
        },
        "ck_product_events_name": {
            "event_name",
            "living_loop_today_viewed",
            "living_loop_decision_viewed",
            "living_loop_choice_previewed",
            "living_loop_immediate_result_viewed",
            "living_loop_delayed_result_viewed",
            "living_loop_enter_town_clicked",
            "living_loop_city_pulse_opened",
            "living_loop_choice_confirmed",
            "living_loop_result_settled",
            "living_loop_result_first_viewed",
        },
    }
    for table in ("living_loop_days", "product_events"):
        for name, definition in contract[table]["checks"].items():
            normalized = " ".join(definition.lower().split())
            assert all(token in normalized for token in check_tokens[name])
    assert contract["living_loop_days"]["primary_key"]["constrained_columns"] == [
        "id"
    ]
    assert contract["product_events"]["primary_key"]["constrained_columns"] == [
        "id"
    ]
    for table in ("living_loop_days", "product_events"):
        foreign_keys = contract[table]["foreign_keys"]
        assert len(foreign_keys) == 1
        assert foreign_keys[0]["constrained_columns"] == ["user_id"]
        assert foreign_keys[0]["referred_table"] == "users"
        assert foreign_keys[0]["referred_columns"] == ["id"]
        assert foreign_keys[0]["options"].get("ondelete") == "CASCADE"

    types = {(row[0], row[1]): row[2] for row in type_rows}
    assert {key for key, value in types.items() if value == "json"} == JSON_COLUMNS
    assert {
        key for key, value in types.items() if value == "timestamp with time zone"
    } == TIMESTAMPTZ_COLUMNS


async def _new_user(session: AsyncSession, label: str) -> User:
    user = User(
        name=f"Living Loop PG {label}",
        email=f"living-loop-pg-{label}-{uuid4().hex}@example.test",
        soul_coin_balance=137,
    )
    session.add(user)
    await session.flush()
    return user


def _day(
    user_id: str,
    day_key: date,
    *,
    choice_key: str | None = None,
    idempotency_key: str | None = None,
    observed_at: datetime | None = None,
) -> LivingLoopDay:
    state = "chosen" if choice_key is not None else "pending"
    return LivingLoopDay(
        user_id=user_id,
        experiment_key="living_loop_p0",
        day_key=day_key,
        scenario_key="plaza_supply_dispute",
        scenario_version=1,
        state=state,
        scenario_snapshot_json={
            "unicode": "星港居民",
            "nested": {"list": [1, True, None]},
        },
        choice_key=choice_key,
        choice_idempotency_key=idempotency_key,
        immediate_result_json={"accepted": True, "nullable": None},
        delayed_result_json={"effects": ["信任", "秩序"]},
        first_viewed_at=observed_at,
        choice_confirmed_at=observed_at if choice_key else None,
        result_available_at=(observed_at + timedelta(seconds=60))
        if observed_at is not None and choice_key
        else None,
    )


def _event(user_id: str, observed_at: datetime) -> ProductEvent:
    return ProductEvent(
        event_id=str(uuid4()),
        user_id=user_id,
        session_id=str(uuid4()),
        event_name="living_loop_today_viewed",
        properties_json={
            "unicode": "星港事件",
            "nested": {"list": [1, False, None]},
            "nullable": None,
        },
        occurred_at=observed_at,
        client_occurred_at=observed_at,
        created_at=observed_at,
    )


def _assert_constraint(error: IntegrityError, expected: str) -> None:
    cause = getattr(error.orig, "__cause__", None)
    actual = getattr(cause, "constraint_name", None)
    assert actual == expected or expected in str(error), (
        f"expected PostgreSQL constraint {expected!r}, got {actual!r}: {error}"
    )


async def _expect_integrity(
    factory: async_sessionmaker[AsyncSession],
    row: LivingLoopDay,
    expected_constraint: str,
) -> None:
    async with factory() as session:
        session.add(row)
        with pytest.raises(IntegrityError) as caught:
            await session.commit()
        _assert_constraint(caught.value, expected_constraint)
        await session.rollback()


async def _roundtrip_and_constraints(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    source_time = datetime(
        2026,
        8,
        28,
        12,
        34,
        56,
        123456,
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    )
    idempotency_key = str(uuid4())
    async with factory() as session:
        first = await _new_user(session, "roundtrip-a")
        second = await _new_user(session, "roundtrip-b")
        first_id, second_id = first.id, second.id
        day = _day(
            first_id,
            date(2026, 8, 28),
            choice_key="public_support",
            idempotency_key=idempotency_key,
            observed_at=source_time,
        )
        event = _event(first_id, source_time)
        session.add_all([day, event])
        await session.commit()
        day_id, event_id = day.id, event.id

    async with factory() as session:
        loaded_day = await session.get(LivingLoopDay, day_id)
        loaded_event = await session.get(ProductEvent, event_id)
        assert loaded_day is not None and loaded_event is not None
        assert loaded_day.scenario_snapshot_json == {
            "unicode": "星港居民",
            "nested": {"list": [1, True, None]},
        }
        assert loaded_day.immediate_result_json == {
            "accepted": True,
            "nullable": None,
        }
        assert loaded_day.delayed_result_json == {"effects": ["信任", "秩序"]}
        assert loaded_event.properties_json == {
            "unicode": "星港事件",
            "nested": {"list": [1, False, None]},
            "nullable": None,
        }
        expected_utc = source_time.astimezone(UTC)
        for value in (
            loaded_day.first_viewed_at,
            loaded_day.choice_confirmed_at,
            loaded_event.occurred_at,
            loaded_event.client_occurred_at,
            loaded_event.created_at,
        ):
            assert value is not None and value.tzinfo is not None
            assert value.astimezone(UTC) == expected_utc

    await _expect_integrity(
        factory,
        _day(
            second_id,
            date(2026, 8, 29),
            choice_key="private_mediation",
            idempotency_key=idempotency_key,
        ),
        "uq_living_loop_days_choice_idempotency_key",
    )
    await _expect_integrity(
        factory,
        _day(first_id, date(2026, 8, 28)),
        "uq_living_loop_day_user_experiment_day",
    )
    await _expect_integrity(
        factory,
        _day(
            second_id,
            date(2026, 8, 30),
            idempotency_key=str(uuid4()),
        ),
        "ck_living_loop_days_choice_idempotency",
    )


async def _concurrency_contract(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        user = await _new_user(session, "concurrency")
        resident = Resident(
            slug=f"living-loop-pg-{uuid4().hex}",
            name="并发居民",
            creator_id=user.id,
            district="harbor",
            status="idle",
            resident_type="player",
            sprite_key="伊莎贝拉",
        )
        session.add(resident)
        await session.flush()
        user.player_resident_id = resident.id
        await session.commit()
        user_id = user.id

    async def load_today():
        async with factory() as session:
            return await get_today(session, user_id)

    today_results = await asyncio.gather(*(load_today() for _ in range(8)))
    decision_ids = {result["decision"]["id"] for result in today_results}
    assert len(decision_ids) == 1
    decision_id = decision_ids.pop()

    async with factory() as session:
        day_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(LivingLoopDay)
                    .where(LivingLoopDay.user_id == user_id)
                )
            ).scalar_one()
        )
    assert day_count == 1

    keys = [str(uuid4()), str(uuid4())]
    choices = ["public_support", "private_mediation"]

    async def make_choice(choice_key: str, idempotency_key: str) -> int:
        async with factory() as session:
            try:
                await choose(
                    session,
                    user_id=user_id,
                    decision_id=decision_id,
                    choice_key=choice_key,
                    idempotency_key=idempotency_key,
                )
                return 200
            except LivingLoopError as error:
                return error.status_code

    statuses = await asyncio.gather(
        *(make_choice(choice, key) for choice, key in zip(choices, keys, strict=True))
    )
    assert sorted(statuses) == [200, 409]

    async with factory() as session:
        persisted = await session.get(LivingLoopDay, decision_id)
        assert persisted is not None
        assert persisted.choice_key in choices
        assert persisted.choice_idempotency_key in keys
        assert (persisted.choice_key, persisted.choice_idempotency_key) in set(
            zip(choices, keys, strict=True)
        )
        winning_choice = str(persisted.choice_key)
        winning_key = str(persisted.choice_idempotency_key)
        choice_events = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ProductEvent)
                    .where(
                        ProductEvent.user_id == user_id,
                        ProductEvent.event_name == "living_loop_choice_confirmed",
                    )
                )
            ).scalar_one()
        )
        assert choice_events == 1

    async with factory() as session:
        replay = await choose(
            session,
            user_id=user_id,
            decision_id=decision_id,
            choice_key=winning_choice,
            idempotency_key=winning_key,
        )
    assert replay["decision"]["id"] == decision_id

    async with factory() as session:
        assert int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ProductEvent)
                    .where(
                        ProductEvent.user_id == user_id,
                        ProductEvent.event_name == "living_loop_choice_confirmed",
                    )
                )
            ).scalar_one()
        ) == 1


async def _cascade_and_account_cleanup(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(UTC)

    async with factory() as session:
        cascade_user = await _new_user(session, "cascade")
        cascade_id = cascade_user.id
        session.add_all(
            [
                _day(cascade_id, date(2026, 8, 31)),
                _event(cascade_id, now),
            ]
        )
        await session.commit()
    async with factory() as session:
        await session.execute(
            text("DELETE FROM users WHERE id=:user_id"), {"user_id": cascade_id}
        )
        await session.commit()
    async with factory() as session:
        assert int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(LivingLoopDay)
                    .where(LivingLoopDay.user_id == cascade_id)
                )
            ).scalar_one()
        ) == 0
        assert int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ProductEvent)
                    .where(ProductEvent.user_id == cascade_id)
                )
            ).scalar_one()
        ) == 0

    async with factory() as session:
        account_user = await _new_user(session, "account-delete")
        account_id, account_email = account_user.id, account_user.email
        session.add_all(
            [
                _day(account_id, date(2026, 9, 1)),
                _event(account_id, now),
            ]
        )
        await session.commit()
        await delete_account(session, account_user, account_email)
    async with factory() as session:
        assert await session.get(User, account_id) is None
        assert int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(LivingLoopDay)
                    .where(LivingLoopDay.user_id == account_id)
                )
            ).scalar_one()
        ) == 0
        assert int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ProductEvent)
                    .where(ProductEvent.user_id == account_id)
                )
            ).scalar_one()
        ) == 0


async def test_living_loop_p0_real_postgres_acceptance(monkeypatch) -> None:
    monkeypatch.setattr(settings, "living_loop_p0_enabled", True)
    monkeypatch.setattr(settings, "living_loop_p0_delay_seconds", 60)

    async with _fresh_database() as database_url:
        env = {
            **os.environ,
            "DATABASE_URL": database_url,
            "DEBUG": "true",
            "RUN_BACKGROUND_TASKS": "false",
            "AGENT_ENABLED": "false",
        }
        blank = create_async_engine(database_url)
        try:
            async with blank.connect() as connection:
                assert (
                    await connection.execute(
                        text("SELECT to_regclass('public.alembic_version')")
                    )
                ).scalar_one_or_none() is None
        finally:
            await blank.dispose()

        _alembic(env, "upgrade", "068_fix_theater_bounds")
        engine = create_async_engine(database_url)
        try:
            assert await _revision(engine) == "068_fix_theater_bounds"
            tables_at_068 = await _table_names(engine)
            assert "users" in tables_at_068
            assert "living_loop_days" not in tables_at_068
            assert "product_events" not in tables_at_068
            factory = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            async with factory() as session:
                sentinel = await _new_user(session, "migration-sentinel")
                await session.commit()
                sentinel_id = sentinel.id
        finally:
            await engine.dispose()

        _alembic(env, "upgrade", "069_living_loop_p0")
        engine = create_async_engine(database_url)
        try:
            assert await _revision(engine) == "069_living_loop_p0"
            assert await _table_names(engine) == tables_at_068 | {
                "living_loop_days",
                "product_events",
            }
            await _assert_schema(engine)
        finally:
            await engine.dispose()

        _alembic(env, "downgrade", "068_fix_theater_bounds")
        engine = create_async_engine(database_url)
        try:
            assert await _revision(engine) == "068_fix_theater_bounds"
            assert await _table_names(engine) == tables_at_068
            async with engine.connect() as connection:
                assert int(
                    (
                        await connection.execute(
                            text("SELECT count(*) FROM users WHERE id=:id"),
                            {"id": sentinel_id},
                        )
                    ).scalar_one()
                ) == 1
        finally:
            await engine.dispose()

        _alembic(env, "upgrade", "069_living_loop_p0")
        engine = create_async_engine(database_url, pool_size=20, max_overflow=20)
        try:
            assert await _revision(engine) == "069_living_loop_p0"
            await _assert_schema(engine)
            async with engine.connect() as connection:
                full_version, server_version, server_version_num, database = (
                    await connection.execute(
                        text(
                            "SELECT version(), current_setting('server_version'), "
                            "current_setting('server_version_num'), current_database()"
                        )
                    )
                ).one()
            assert int(server_version_num) // 10000 == 16
            print(f"PG_VERSION={server_version}")
            print(f"PG_VERSION_NUM={server_version_num}")
            print(f"PG_VERSION_FULL={full_version}")
            print(f"PG_DATABASE={database}")

            await _roundtrip_and_constraints(engine)
            await _concurrency_contract(engine)
            await _cascade_and_account_cleanup(engine)
            print("MIGRATION_SEQUENCE=068->069->068->069 PASS")
            print("PG_CATALOG_JSON_TIMESTAMPTZ=PASS")
            print("PG_CONSTRAINTS_IDEMPOTENCY=PASS")
            print("PG_CONCURRENCY_SINGLE_WRITE=PASS")
            print("PG_CASCADE_ACCOUNT_CLEANUP=PASS")
        finally:
            await engine.dispose()
