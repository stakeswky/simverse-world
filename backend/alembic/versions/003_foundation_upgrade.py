"""foundation upgrade: user fields, resident fields, system_config, forge_sessions, pending_messages

Revision ID: 003_foundation_upgrade
Revises: 002_search_reward
Create Date: 2026-04-07

"""
from alembic import op
import sqlalchemy as sa

revision = '003_foundation_upgrade'
down_revision = '002_search_reward'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # User table — 13 new columns                                         #
    # ------------------------------------------------------------------ #
    op.add_column("users", sa.Column("linuxdo_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("linuxdo_trust_level", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("player_resident_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("last_x", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("last_y", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("settings_json", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("custom_llm_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("custom_llm_api_format", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("custom_llm_api_key", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("custom_llm_base_url", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("custom_llm_model", sa.String(length=128), nullable=True))

    # ------------------------------------------------------------------ #
    # Resident table — 3 new columns                                      #
    # ------------------------------------------------------------------ #
    op.add_column("residents", sa.Column("resident_type", sa.String(length=32), nullable=True, server_default="npc"))
    op.add_column("residents", sa.Column("reply_mode", sa.String(length=32), nullable=True, server_default="auto"))
    op.add_column("residents", sa.Column("portrait_url", sa.Text(), nullable=True))

    # ------------------------------------------------------------------ #
    # system_config table                                                  #
    # ------------------------------------------------------------------ #
    op.create_table(
        "system_config",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("group", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )

    # ------------------------------------------------------------------ #
    # forge_sessions table                                                 #
    # ------------------------------------------------------------------ #
    op.create_table(
        "forge_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("character_name", sa.String(length=128), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=True, server_default="guided"),
        sa.Column("status", sa.String(length=32), nullable=True, server_default="collecting"),
        sa.Column("current_stage", sa.Integer(), nullable=True, server_default="1"),
        sa.Column("answers_json", sa.Text(), nullable=True),
        sa.Column("ability_json", sa.Text(), nullable=True),
        sa.Column("persona_json", sa.Text(), nullable=True),
        sa.Column("soul_json", sa.Text(), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------ #
    # pending_messages table                                               #
    # ------------------------------------------------------------------ #
    op.create_table(
        "pending_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("is_auto_reply", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Drop new tables
    op.drop_table("pending_messages")
    op.drop_table("forge_sessions")
    op.drop_table("system_config")

    # Drop resident columns
    op.drop_column("residents", "portrait_url")
    op.drop_column("residents", "reply_mode")
    op.drop_column("residents", "resident_type")

    # Drop user columns
    op.drop_column("users", "custom_llm_model")
    op.drop_column("users", "custom_llm_base_url")
    op.drop_column("users", "custom_llm_api_key")
    op.drop_column("users", "custom_llm_api_format")
    op.drop_column("users", "custom_llm_enabled")
    op.drop_column("users", "settings_json")
    op.drop_column("users", "last_y")
    op.drop_column("users", "last_x")
    op.drop_column("users", "player_resident_id")
    op.drop_column("users", "is_banned")
    op.drop_column("users", "is_admin")
    op.drop_column("users", "linuxdo_trust_level")
    op.drop_column("users", "linuxdo_id")
