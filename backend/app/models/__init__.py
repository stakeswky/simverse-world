"""Import every model module so Base.metadata / mapper configuration is
complete in any process that touches the ORM (API, agent-worker, scripts).

Mapper configuration resolves cross-table FKs lazily at first query; a process
that only imports some models (e.g. the agent-worker) blows up with
NoReferencedTableError on relationships into un-imported tables.
"""
import app.models.user  # noqa: F401
import app.models.resident  # noqa: F401
import app.models.resident_sprite_run  # noqa: F401
import app.models.conversation  # noqa: F401
import app.models.transaction  # noqa: F401
import app.models.system_config  # noqa: F401
import app.models.forge_session  # noqa: F401
import app.models.pending_message  # noqa: F401
import app.models.memory  # noqa: F401
import app.models.personality_history  # noqa: F401
import app.models.llm_usage  # noqa: F401
import app.models.world_event  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.achievement  # noqa: F401
import app.models.shop  # noqa: F401
import app.models.location_visit  # noqa: F401
import app.models.digest  # noqa: F401
import app.models.daily_quest  # noqa: F401
import app.models.commission  # noqa: F401
import app.models.resident_goal  # noqa: F401
import app.models.bulletin_post  # noqa: F401
import app.models.time_capsule  # noqa: F401
import app.models.feed  # noqa: F401
import app.models.season  # noqa: F401
import app.models.goal_investment  # noqa: F401
import app.models.debate  # noqa: F401
# Lab (experiment building) core — P1
import app.models.coin_hold  # noqa: F401
import app.models.coin_hold_entry  # noqa: F401
import app.models.lab_terminalization  # noqa: F401
import app.models.resident_treasury  # noqa: F401
import app.models.lab_task  # noqa: F401
import app.models.lab_run  # noqa: F401
import app.models.lab_artifact  # noqa: F401
# World governance overlay — P3
import app.models.world_change_proposal  # noqa: F401
import app.models.dynamic_location  # noqa: F401
import app.models.dynamic_mechanic  # noqa: F401
# Lab Agent v1 — grant/policy/broker/ledger protocol contracts (P0, T1)
import app.models.lab_event  # noqa: F401
import app.models.lab_grant  # noqa: F401
import app.models.lab_action  # noqa: F401
import app.models.lab_lease  # noqa: F401
import app.models.lab_budget  # noqa: F401
import app.models.lab_worker_attempt  # noqa: F401
import app.models.world_revision  # noqa: F401
# Lab Agent protocol v2 durable Gateway state (migration 039)
import app.models.lab_runtime  # noqa: F401
import app.models.lab_control  # noqa: F401
# Realism P2 — numeric two-axis relationships (§7.1)
import app.models.resident_relation  # noqa: F401
# S2-1 offices — unified job/office table (职位实体化)
import app.models.office  # noqa: F401
# S1-3 议题立场与舆论动力学 — bounded-confidence issue stances
import app.models.issue_stance  # noqa: F401
# S1-5 镇财政闭环 — the town's public account (third account kind)
import app.models.town_treasury  # noqa: F401
import app.models.town_treasury_entry  # noqa: F401
import app.models.caravan_visit  # noqa: F401
import app.models.market  # noqa: F401
import app.models.economy_bootstrap  # noqa: F401
# S2-5 policies — typed/tiered/versioned policy table (四级分级审批)
import app.models.policy  # noqa: F401
# F2 公民权档位变更历史 —— 可回滚硬门 + 公民时钟锚点的载体
import app.models.civic_standing_history  # noqa: F401
# Headless external players and their scoped opaque credentials.
import app.models.agent_player  # noqa: F401
import app.models.hosted_agent  # noqa: F401
# Living Loop P0 — durable daily decisions and privacy-bounded product events.
import app.models.living_loop_day  # noqa: F401
import app.models.product_event  # noqa: F401
