"""Add Living Loop P0 decisions and privacy-bounded product events.

Revision ID: 069_living_loop_p0
Revises: 068_fix_theater_bounds
Create Date: 2026-08-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "069_living_loop_p0"
down_revision = "068_fix_theater_bounds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "living_loop_days",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("experiment_key", sa.String(length=64), nullable=False),
        sa.Column("day_key", sa.Date(), nullable=False),
        sa.Column("scenario_key", sa.String(length=100), nullable=False),
        sa.Column("scenario_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("scenario_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("choice_key", sa.String(length=64), nullable=True),
        sa.Column("choice_idempotency_key", sa.String(length=36), nullable=True),
        sa.Column("immediate_result_json", sa.JSON(), nullable=True),
        sa.Column("delayed_result_json", sa.JSON(), nullable=True),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("choice_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "experiment_key = 'living_loop_p0'",
            name="ck_living_loop_days_experiment",
        ),
        sa.CheckConstraint(
            "scenario_version = 1",
            name="ck_living_loop_days_scenario_version",
        ),
        sa.CheckConstraint(
            "state IN ('pending','chosen','result_ready','result_viewed')",
            name="ck_living_loop_days_state",
        ),
        sa.CheckConstraint(
            "choice_key IS NULL OR choice_key IN "
            "('public_support','private_mediation','collect_evidence')",
            name="ck_living_loop_days_choice",
        ),
        sa.CheckConstraint(
            "choice_idempotency_key IS NULL OR choice_key IS NOT NULL",
            name="ck_living_loop_days_choice_idempotency",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "experiment_key",
            "day_key",
            name="uq_living_loop_day_user_experiment_day",
        ),
        sa.UniqueConstraint(
            "choice_idempotency_key",
            name="uq_living_loop_days_choice_idempotency_key",
        ),
    )
    op.create_index(
        "ix_living_loop_days_user_id",
        "living_loop_days",
        ["user_id"],
    )

    op.create_table(
        "product_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("event_name", sa.String(length=80), nullable=False),
        sa.Column("properties_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_name IN ("
            "'living_loop_today_viewed',"
            "'living_loop_decision_viewed',"
            "'living_loop_choice_previewed',"
            "'living_loop_immediate_result_viewed',"
            "'living_loop_delayed_result_viewed',"
            "'living_loop_enter_town_clicked',"
            "'living_loop_city_pulse_opened',"
            "'living_loop_choice_confirmed',"
            "'living_loop_result_settled',"
            "'living_loop_result_first_viewed'"
            ")",
            name="ck_product_events_name",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_product_events_event_id"),
    )
    op.create_index("ix_product_events_user_id", "product_events", ["user_id"])
    op.create_index(
        "ix_product_events_session_id", "product_events", ["session_id"]
    )
    op.create_index(
        "ix_product_events_event_name", "product_events", ["event_name"]
    )
    op.create_index(
        "ix_product_events_occurred_at", "product_events", ["occurred_at"]
    )
    op.create_index(
        "ix_product_events_created_at", "product_events", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_product_events_created_at", table_name="product_events")
    op.drop_index("ix_product_events_occurred_at", table_name="product_events")
    op.drop_index("ix_product_events_event_name", table_name="product_events")
    op.drop_index("ix_product_events_session_id", table_name="product_events")
    op.drop_index("ix_product_events_user_id", table_name="product_events")
    op.drop_table("product_events")
    op.drop_index("ix_living_loop_days_user_id", table_name="living_loop_days")
    op.drop_table("living_loop_days")
