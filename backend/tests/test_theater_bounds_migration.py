"""P3 批 2:存量剧院坐标收进 walkable 域(迁移;与开闸分属不同批次)。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from app.world_geometry import WALKABLE_X_RANGE, WALKABLE_Y_RANGE

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "alembic" / "versions" / "068_fix_theater_bounds.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_068", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _table(metadata):
    return sa.Table(
        "dynamic_locations", metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("slug", sa.String),
        sa.Column("data_json", sa.JSON),
    )


def test_068_chains_after_067_and_repository_has_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    script = ScriptDirectory.from_config(Config(str(ini)))
    assert script.get_heads() == ["069_living_loop_p0"]
    rev = script.get_revision("068_fix_theater_bounds")
    assert rev.down_revision == "067_market_economy_loop"
    assert len(rev.revision) <= 32


def test_068_moves_theater_into_the_walkable_band_and_is_idempotent():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    rows = _table(metadata)
    metadata.create_all(engine)

    old = {"name": "剧院", "type": "public", "role": "culture",
           "bounds": [172, 40, 178, 50], "center": [175, 45],
           "entrance": [172, 45],
           "description": "小镇剧院:说书、演展、故事会的舞台",
           "boosted_actions": ["CHAT_RESIDENT", "OBSERVE"]}
    other = {"name": "邮局", "type": "public", "bounds": [44, 100, 48, 106]}
    with engine.begin() as conn:
        conn.execute(rows.insert(), [
            {"id": "t", "slug": "theater", "data_json": old},
            {"id": "p", "slug": "post_office", "data_json": other},
        ])
        assert module._rewrite(conn, module._NEW, module._OLD) == 1
        assert module._rewrite(conn, module._NEW, module._OLD) == 0, "幂等"
        stored = dict(conn.execute(
            sa.select(rows.c.slug, rows.c.data_json)).all())

    theater = stored["theater"]
    assert theater["bounds"] == [168, 40, 173, 50]
    assert theater["center"] == [170, 45]
    assert theater["entrance"] == [172, 45], "入口不动 —— 实测它可达"
    for key in ("name", "type", "role", "description", "boosted_actions"):
        assert theater[key] == old[key], f"{key} 不该被迁移碰"
    assert stored["post_office"] == other, "只动剧院这一行"

    x1, y1, x2, y2 = theater["bounds"]
    assert x1 in WALKABLE_X_RANGE and x2 in WALKABLE_X_RANGE
    assert y1 in WALKABLE_Y_RANGE and y2 in WALKABLE_Y_RANGE
    assert theater["center"][0] in WALKABLE_X_RANGE
    ex, ey = theater["entrance"]
    assert x1 <= ex <= x2 and y1 <= ey <= y2, \
        "entrance 必须仍落在新 bounds 内(apply.py:78-84 会判它)"


def test_068_downgrade_restores_the_original_and_skips_foreign_shapes():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    rows = _table(metadata)
    metadata.create_all(engine)

    hand_edited = {"name": "剧院", "type": "public",
                   "bounds": [100, 40, 105, 50], "center": [102, 45]}
    with engine.begin() as conn:
        conn.execute(rows.insert(),
                     [{"id": "t", "slug": "theater", "data_json": hand_edited}])
        assert module._rewrite(conn, module._NEW, module._OLD) == 0, \
            "生产被手工动过的行不许被盲目覆盖"
        conn.execute(rows.update().values(data_json={
            "name": "剧院", "type": "public",
            "bounds": [168, 40, 173, 50], "center": [170, 45]}))
        assert module._rewrite(conn, module._OLD, module._NEW) == 1
        back = conn.execute(sa.select(rows.c.data_json)).scalar_one()
    assert back["bounds"] == [172, 40, 178, 50]
    assert back["center"] == [175, 45]


def test_068_is_a_noop_without_the_row():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    _table(metadata)
    metadata.create_all(engine)
    with engine.begin() as conn:
        assert module._rewrite(conn, module._NEW, module._OLD) == 0
