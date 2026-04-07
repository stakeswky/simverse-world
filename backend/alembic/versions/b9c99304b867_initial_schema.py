"""initial schema

Revision ID: b9c99304b867
Revises:
Create Date: 2026-04-07 16:02:16.219233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9c99304b867'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'users',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=True),
        sa.Column('github_id', sa.String(50), nullable=True, unique=True),
        sa.Column('avatar', sa.String(500), nullable=True),
        sa.Column('soul_coin_balance', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'residents',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('district', sa.String(50), nullable=False, server_default='free'),
        sa.Column('status', sa.String(20), nullable=False, server_default='idle'),
        sa.Column('heat', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('model_tier', sa.String(20), nullable=False, server_default='standard'),
        sa.Column('token_cost_per_turn', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('creator_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('ability_md', sa.Text(), nullable=False, server_default=''),
        sa.Column('persona_md', sa.Text(), nullable=False, server_default=''),
        sa.Column('soul_md', sa.Text(), nullable=False, server_default=''),
        sa.Column('meta_json', sa.JSON(), nullable=True),
        sa.Column('sprite_key', sa.String(100), nullable=False, server_default='伊莎贝拉'),
        sa.Column('tile_x', sa.Integer(), nullable=False, server_default='76'),
        sa.Column('tile_y', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('star_rating', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('total_conversations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_rating', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_conversation_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_residents_slug', 'residents', ['slug'], unique=True)
    op.create_index('ix_residents_creator_id', 'residents', ['creator_id'])

    op.create_table(
        'conversations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('resident_id', sa.String(), sa.ForeignKey('residents.id'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('turns', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rating', sa.Integer(), nullable=True),
    )
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])
    op.create_index('ix_conversations_resident_id', 'conversations', ['resident_id'])

    op.create_table(
        'messages',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])

    op.create_table(
        'transactions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_transactions_user_id', 'transactions', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('transactions')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('residents')
    op.drop_table('users')
