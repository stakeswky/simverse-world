import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import models so alembic sees them
from app.database import Base
from app.models.user import User
from app.models.resident import Resident
from app.models.resident_sprite_run import ResidentSpriteRun
from app.models.conversation import Conversation, Message
from app.models.transaction import Transaction
from app.models.llm_usage import LLMUsage
from app.models.world_event import WorldEvent
from app.models.caravan_visit import CaravanVisit, CaravanVisitPurchase
from app.models.notification import Notification
from app.models.achievement import Achievement, UserAchievement
from app.models.shop import Item, Purchase
from app.models.location_visit import LocationVisit
from app.models.digest import Digest
from app.models.daily_quest import DailyQuest
from app.models.commission import Commission
from app.models.resident_goal import ResidentGoal
from app.models.bulletin_post import BulletinPost
from app.models.time_capsule import TimeCapsule
from app.models.feed import Follow, FeedEvent
from app.models.season import Season, SeasonScript, Poll, Vote, SeasonScore
from app.models.goal_investment import GoalInvestment
from app.models.debate import Debate, DebateStake
# C3 剧本季 reuses the seasons family (027) — no new migration.
# Lab (experiment building) core — P1 (migration 032)
from app.models.coin_hold import CoinHold
from app.models.resident_treasury import ResidentTreasury
from app.models.lab_task import LabTask
from app.models.lab_run import LabRun, LabRunStep
from app.models.lab_artifact import LabArtifact
# World governance overlay — P3 (migration 033)
from app.models.world_change_proposal import WorldChangeProposal
from app.models.dynamic_location import DynamicLocation
from app.models.dynamic_mechanic import DynamicMechanic
# Lab Agent v1 — grant/policy/broker/ledger protocol contracts (migration 034)
from app.models.lab_event import LabRunEvent, OutboxEvent
from app.models.lab_grant import LabCapabilityGrant
from app.models.lab_action import LabToolAction, LabApproval
from app.models.lab_lease import LabRunLease
from app.models.lab_budget import LabRunBudget
from app.models.world_revision import WorldRevision
from app.models.resident_relation import ResidentRelation
from app.models.living_loop_day import LivingLoopDay
from app.models.product_event import ProductEvent

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from app.config import settings

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.database_url
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
