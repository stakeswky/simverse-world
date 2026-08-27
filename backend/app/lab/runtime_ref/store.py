"""Durable, Runtime-local protocol-v2 state backed by SQLite.

This store owns model-side session/checkpoint state, replayable provider events,
pending intent bindings, artifacts, and service-command deduplication.  It does
not replace the Gateway's PostgreSQL turn/action/event truth.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

import aiosqlite

from app.lab.protocol import (
    MAX_EVENT_BYTES,
    MAX_UNACKED_BYTES,
    MAX_UNACKED_EVENTS,
    RuntimeEvent,
)
from app.lab.runtime_ref.service_auth import MAX_REQUEST_BYTES, canonical_json_bytes
from app.lab.runtime_ref.spool import ArtifactSpool, ArtifactSpoolError, SpooledArtifact


STORE_VERSION = 3
SESSION_STATES = frozenset({
    "created", "running", "intent_pending", "resuming", "completed", "failed",
    "cancelled", "fenced", "quarantined",
})
INTENT_STATES = frozenset({"pending", "result_recorded", "applied"})
COMMAND_STATES = frozenset({"accepted", "completed"})
RESULT_OUTCOMES = frozenset({"succeeded", "denied", "failed"})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_UNSET = object()


class RuntimeStoreError(RuntimeError):
    pass


class RuntimeStoreConflict(RuntimeStoreError):
    pass


class RuntimeStoreNotFound(RuntimeStoreError):
    pass


class CrossBindingReplay(RuntimeStoreConflict):
    """A jti or command id was reused outside its original exact binding."""


class RuntimeStoreBackpressure(RuntimeStoreConflict):
    """The Runtime must wait for a committed Gateway event ACK."""


@dataclass(frozen=True)
class StoredSession:
    session_id: str
    run_id: str
    client_run_id: str
    epoch: int
    scopes: tuple[str, ...]
    budget_usd: float
    egress_allowlist: tuple[str, ...]
    state: str
    checkpoint: Any | None
    next_event_cursor: int
    acked_event_cursor: int


@dataclass(frozen=True)
class StoredEvent:
    session_id: str
    cursor: int
    event_id: str
    event_kind: str
    turn_id: str | None
    intent_id: str | None
    outcome: str | None
    tool_name: str | None
    tool_args: Any | None
    tool_args_digest: str | None
    payload: Any
    dedupe_key: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class StoredIntent:
    session_id: str
    turn_id: str
    intent_id: str
    tool: str
    args: Any
    state: str
    result_digest: str | None
    result_outcome: str | None
    result_payload: Any | None
    result_command_id: str | None
    result_action_id: str | None


@dataclass(frozen=True)
class StoredArtifact:
    session_id: str
    artifact_id: str
    kind: str
    title: str
    uri: str | None
    text_md: str | None
    meta: Any
    artifact_digest: str
    content_type: str
    original_filename: str | None
    declared_byte_size: int | None
    expected_sha256: str | None
    required: bool
    producer_action_id: str | None
    spool_locator: str | None
    upload_state: str
    upload_command: Any | None
    upload_command_digest: str | None
    upload_id: str | None
    upload_receipt: Any | None
    upload_receipt_digest: str | None
    upload_attempts: int
    last_upload_error: str | None
    upload_acked_at: datetime | None
    spool_deleted_at: datetime | None


@dataclass(frozen=True)
class CommandBinding:
    audience: str
    command_id: str
    jti: str
    request_digest: str
    run_id: str
    session_id: str
    epoch: int
    action: str


@dataclass(frozen=True)
class StoredCommandReceipt:
    receipt_id: str
    binding: CommandBinding
    state: str
    response: Any | None


@dataclass(frozen=True)
class CommandClaim:
    receipt: StoredCommandReceipt
    is_retry: bool


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS runtime_sessions (
        session_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        client_run_id TEXT NOT NULL,
        epoch INTEGER NOT NULL CHECK (epoch >= 0),
        scopes_json TEXT NOT NULL,
        budget_usd REAL NOT NULL CHECK (budget_usd >= 0),
        egress_allowlist_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN (
            'created', 'running', 'intent_pending', 'resuming', 'completed',
            'failed', 'cancelled', 'fenced', 'quarantined'
        )),
        checkpoint_json TEXT,
        next_event_cursor INTEGER NOT NULL DEFAULT 1 CHECK (next_event_cursor >= 1),
        acked_event_cursor INTEGER NOT NULL DEFAULT 0 CHECK (acked_event_cursor >= 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (client_run_id, epoch),
        UNIQUE (run_id, epoch)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_events (
        session_id TEXT NOT NULL REFERENCES runtime_sessions(session_id) ON DELETE CASCADE,
        cursor INTEGER NOT NULL CHECK (cursor >= 1),
        event_id TEXT NOT NULL UNIQUE,
        event_kind TEXT NOT NULL,
        turn_id TEXT,
        intent_id TEXT,
        outcome TEXT,
        tool_name TEXT,
        tool_args_json TEXT,
        tool_args_digest TEXT,
        payload_json TEXT NOT NULL,
        event_digest TEXT NOT NULL,
        event_bytes INTEGER NOT NULL CHECK (event_bytes > 0),
        dedupe_key TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (session_id, cursor),
        UNIQUE (session_id, dedupe_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_intents (
        session_id TEXT NOT NULL REFERENCES runtime_sessions(session_id) ON DELETE CASCADE,
        turn_id TEXT NOT NULL,
        intent_id TEXT NOT NULL,
        tool TEXT NOT NULL,
        args_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('pending', 'result_recorded', 'applied')),
        result_digest TEXT,
        result_outcome TEXT CHECK (
            result_outcome IS NULL OR result_outcome IN ('succeeded', 'denied', 'failed')
        ),
        result_payload_json TEXT,
        result_command_id TEXT,
        result_action_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (session_id, intent_id),
        UNIQUE (session_id, turn_id)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_runtime_active_intent
    ON runtime_intents(session_id) WHERE state IN ('pending', 'result_recorded')
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_artifacts (
        session_id TEXT NOT NULL REFERENCES runtime_sessions(session_id) ON DELETE CASCADE,
        artifact_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        uri TEXT,
        text_md TEXT,
        meta_json TEXT NOT NULL,
        artifact_digest TEXT NOT NULL,
        content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
        original_filename TEXT,
        declared_byte_size INTEGER CHECK (
            declared_byte_size IS NULL OR declared_byte_size >= 0
        ),
        expected_sha256 TEXT CHECK (
            expected_sha256 IS NULL OR length(expected_sha256) = 64
        ),
        required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0, 1)),
        producer_action_id TEXT,
        spool_locator TEXT,
        upload_state TEXT NOT NULL DEFAULT 'legacy_inline' CHECK (upload_state IN (
            'legacy_inline', 'pending', 'uploading', 'uploaded',
            'acknowledged', 'failed'
        )),
        upload_command_json TEXT,
        upload_command_digest TEXT CHECK (
            upload_command_digest IS NULL OR length(upload_command_digest) = 64
        ),
        upload_id TEXT,
        upload_receipt_json TEXT,
        upload_receipt_digest TEXT CHECK (
            upload_receipt_digest IS NULL OR length(upload_receipt_digest) = 64
        ),
        upload_attempts INTEGER NOT NULL DEFAULT 0 CHECK (upload_attempts >= 0),
        last_upload_error TEXT,
        upload_acked_at TEXT,
        spool_deleted_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (session_id, artifact_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_command_receipts (
        jti TEXT PRIMARY KEY,
        audience TEXT NOT NULL,
        command_id TEXT NOT NULL,
        request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
        run_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        epoch INTEGER NOT NULL CHECK (epoch >= 0),
        action TEXT NOT NULL,
        receipt_id TEXT NOT NULL UNIQUE,
        state TEXT NOT NULL CHECK (state IN ('accepted', 'completed')),
        response_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (audience, command_id),
        CHECK (
            (state = 'accepted' AND response_json IS NULL)
            OR (state = 'completed' AND response_json IS NOT NULL)
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_health (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        checked_at TEXT NOT NULL
    )
    """,
)


_V1_TO_V2_STATEMENTS = (
    "ALTER TABLE runtime_sessions ADD COLUMN acked_event_cursor "
    "INTEGER NOT NULL DEFAULT 0 CHECK (acked_event_cursor >= 0)",
    "ALTER TABLE runtime_events ADD COLUMN tool_name TEXT",
    "ALTER TABLE runtime_events ADD COLUMN tool_args_json TEXT",
    "ALTER TABLE runtime_events ADD COLUMN tool_args_digest TEXT",
    "ALTER TABLE runtime_events ADD COLUMN event_bytes INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE runtime_intents ADD COLUMN result_command_id TEXT",
    "ALTER TABLE runtime_intents ADD COLUMN result_action_id TEXT",
)


_V2_RUNTIME_ARTIFACTS_STATEMENT = """
CREATE TABLE IF NOT EXISTS runtime_artifacts (
    session_id TEXT NOT NULL REFERENCES runtime_sessions(session_id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    uri TEXT,
    text_md TEXT,
    meta_json TEXT NOT NULL,
    artifact_digest TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, artifact_id)
)
"""


_V2_TO_V3_STATEMENTS = (
    "ALTER TABLE runtime_artifacts ADD COLUMN content_type "
    "TEXT NOT NULL DEFAULT 'application/octet-stream'",
    "ALTER TABLE runtime_artifacts ADD COLUMN original_filename TEXT",
    "ALTER TABLE runtime_artifacts ADD COLUMN declared_byte_size INTEGER "
    "CHECK (declared_byte_size IS NULL OR declared_byte_size >= 0)",
    "ALTER TABLE runtime_artifacts ADD COLUMN expected_sha256 TEXT "
    "CHECK (expected_sha256 IS NULL OR length(expected_sha256) = 64)",
    "ALTER TABLE runtime_artifacts ADD COLUMN required INTEGER NOT NULL DEFAULT 1 "
    "CHECK (required IN (0, 1))",
    "ALTER TABLE runtime_artifacts ADD COLUMN producer_action_id TEXT",
    "ALTER TABLE runtime_artifacts ADD COLUMN spool_locator TEXT",
    "ALTER TABLE runtime_artifacts ADD COLUMN upload_state TEXT NOT NULL "
    "DEFAULT 'legacy_inline' CHECK (upload_state IN "
    "('legacy_inline', 'pending', 'uploading', 'uploaded', 'acknowledged', 'failed'))",
    "ALTER TABLE runtime_artifacts ADD COLUMN upload_command_json TEXT",
    "ALTER TABLE runtime_artifacts ADD COLUMN upload_command_digest TEXT "
    "CHECK (upload_command_digest IS NULL OR length(upload_command_digest) = 64)",
    "ALTER TABLE runtime_artifacts ADD COLUMN upload_id TEXT",
    "ALTER TABLE runtime_artifacts ADD COLUMN upload_receipt_json TEXT",
    "ALTER TABLE runtime_artifacts ADD COLUMN upload_receipt_digest TEXT "
    "CHECK (upload_receipt_digest IS NULL OR length(upload_receipt_digest) = 64)",
    "ALTER TABLE runtime_artifacts ADD COLUMN upload_attempts INTEGER NOT NULL DEFAULT 0 "
    "CHECK (upload_attempts >= 0)",
    "ALTER TABLE runtime_artifacts ADD COLUMN last_upload_error TEXT",
    "ALTER TABLE runtime_artifacts ADD COLUMN upload_acked_at TEXT",
    "ALTER TABLE runtime_artifacts ADD COLUMN spool_deleted_at TEXT",
)


def _canonical_text(value: Any) -> str:
    return canonical_json_bytes(value, max_bytes=MAX_REQUEST_BYTES).decode("utf-8")


def _load(value: str | None) -> Any | None:
    return None if value is None else json.loads(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _stored_datetime(value: Any) -> datetime:
    occurred_at = datetime.fromisoformat(str(value).replace(" ", "T"))
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return occurred_at


def _migrated_event_bytes(row: aiosqlite.Row) -> int:
    envelope = RuntimeEvent.model_construct(
        schema_version=2,
        event_id=row["event_id"],
        run_id=row["run_id"],
        session_id=row["session_id"],
        cursor=row["cursor"],
        epoch=row["epoch"],
        event_kind=row["event_kind"],
        turn_id=row["turn_id"],
        intent_id=row["intent_id"],
        outcome=row["outcome"],
        tool_name=row["tool_name"],
        tool_args=_load(row["tool_args_json"]),
        tool_args_digest=row["tool_args_digest"],
        payload=_load(row["payload_json"]),
        occurred_at=_stored_datetime(row["created_at"]),
    ).model_dump(mode="json")
    return len(canonical_json_bytes(envelope, max_bytes=MAX_UNACKED_BYTES))


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is required")


class RuntimeStore:
    """Small transaction-oriented store intended for one session-affine Runtime."""

    def __init__(
        self,
        path: str | Path,
        *,
        artifact_spool_path: str | Path | None = None,
        max_spool_bytes: int = 1024 * 1024 * 1024,
        max_artifact_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        raw_path = str(path)
        if not raw_path or raw_path == ":memory:" or "mode=memory" in raw_path:
            raise ValueError("protocol-v2 runtime_store_path must be a durable file")
        self.path = str(Path(raw_path).expanduser().resolve())
        spool_path = (
            artifact_spool_path
            if artifact_spool_path is not None
            else f"{self.path}.artifacts"
        )
        self.artifact_spool = ArtifactSpool(
            spool_path,
            max_bytes=max_spool_bytes,
            max_artifact_bytes=max_artifact_bytes,
        )
        self._initialized = False
        self._initialize_lock = asyncio.Lock()
        self._artifact_lock = asyncio.Lock()

    def _harden_files(self) -> None:
        if os.name != "posix":
            return
        for candidate in (self.path, f"{self.path}-wal", f"{self.path}-shm"):
            try:
                os.chmod(candidate, 0o600)
            except FileNotFoundError:
                continue

    def _prepare_main_file(self) -> None:
        if os.name != "posix":
            return
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        self._harden_files()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._initialize_lock:
            if self._initialized:
                return
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self._prepare_main_file()
            db = await aiosqlite.connect(self.path, isolation_level=None)
            db.row_factory = aiosqlite.Row
            try:
                await db.execute("PRAGMA foreign_keys = ON")
                await db.execute("PRAGMA journal_mode = WAL")
                await db.execute("PRAGMA busy_timeout = 5000")
                await db.execute("BEGIN IMMEDIATE")
                version = (await (await db.execute("PRAGMA user_version")).fetchone())[0]
                if version not in {0, 1, 2, STORE_VERSION}:
                    raise RuntimeStoreError(
                        f"unsupported runtime store version {version}; expected 1, 2, "
                        f"or {STORE_VERSION}"
                    )
                if version == 1:
                    for statement in _V1_TO_V2_STATEMENTS:
                        await db.execute(statement)
                    migrated_events = await (
                        await db.execute(
                            "SELECT event.*, session.run_id, session.epoch "
                            "FROM runtime_events AS event "
                            "JOIN runtime_sessions AS session "
                            "ON session.session_id = event.session_id "
                            "WHERE event.event_bytes = 0"
                        )
                    ).fetchall()
                    for event in migrated_events:
                        await db.execute(
                            "UPDATE runtime_events SET event_bytes = ? "
                            "WHERE session_id = ? AND cursor = ?",
                            (
                                _migrated_event_bytes(event),
                                event["session_id"],
                                event["cursor"],
                            ),
                        )
                    version = 2
                if version == 2:
                    await db.execute(_V2_RUNTIME_ARTIFACTS_STATEMENT)
                    for statement in _V2_TO_V3_STATEMENTS:
                        await db.execute(statement)
                for statement in _SCHEMA_STATEMENTS:
                    await db.execute(statement)
                await db.execute(f"PRAGMA user_version = {STORE_VERSION}")
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            finally:
                await db.close()
                self._harden_files()
            await self.artifact_spool.initialize()
            self._initialized = True

    async def _connect(self) -> aiosqlite.Connection:
        await self.initialize()
        self._harden_files()
        db = await aiosqlite.connect(self.path, isolation_level=None)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 5000")
        self._harden_files()
        return db

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        db = await self._connect()
        try:
            await db.execute("BEGIN IMMEDIATE")
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()
            self._harden_files()

    @staticmethod
    def _session(row: aiosqlite.Row) -> StoredSession:
        return StoredSession(
            session_id=row["session_id"], run_id=row["run_id"],
            client_run_id=row["client_run_id"], epoch=row["epoch"],
            scopes=tuple(_load(row["scopes_json"]) or []), state=row["state"],
            budget_usd=float(row["budget_usd"]),
            egress_allowlist=tuple(_load(row["egress_allowlist_json"]) or []),
            checkpoint=_load(row["checkpoint_json"]),
            next_event_cursor=row["next_event_cursor"],
            acked_event_cursor=row["acked_event_cursor"],
        )

    async def create_or_get_session(
        self,
        *,
        run_id: str,
        client_run_id: str,
        epoch: int,
        scopes: Iterable[str],
        budget_usd: float = 0.5,
        egress_allowlist: Iterable[str] = (),
        session_id: str | None = None,
        max_active_sessions: int | None = None,
    ) -> StoredSession:
        _require_text("run_id", run_id)
        _require_text("client_run_id", client_run_id)
        if type(epoch) is not int or epoch < 0:
            raise ValueError("epoch must be non-negative")
        normalized_scopes = tuple(sorted(set(scopes)))
        if any(not isinstance(scope, str) or not scope for scope in normalized_scopes):
            raise ValueError("scopes must be non-empty strings")
        if (
            isinstance(budget_usd, bool)
            or not isinstance(budget_usd, (int, float))
            or not math.isfinite(budget_usd)
        ):
            raise ValueError("budget_usd must be finite")
        if budget_usd < 0:
            raise ValueError("budget_usd must be non-negative")
        normalized_egress = tuple(sorted(set(egress_allowlist)))
        if any(not isinstance(host, str) or not host for host in normalized_egress):
            raise ValueError("egress_allowlist must contain non-empty strings")
        scopes_json = _canonical_text(list(normalized_scopes))
        egress_json = _canonical_text(list(normalized_egress))
        async with self._transaction() as db:
            rows = await (
                await db.execute(
                    "SELECT * FROM runtime_sessions "
                    "WHERE (client_run_id = ? AND epoch = ?) OR (run_id = ? AND epoch = ?)",
                    (client_run_id, epoch, run_id, epoch),
                )
            ).fetchall()
            by_id = {row["session_id"]: row for row in rows}
            if len(by_id) > 1:
                raise RuntimeStoreConflict("session binding resolves to multiple rows")
            if by_id:
                existing = self._session(next(iter(by_id.values())))
                if (
                    existing.run_id != run_id
                    or existing.client_run_id != client_run_id
                    or existing.epoch != epoch
                    or existing.scopes != normalized_scopes
                    or existing.budget_usd != float(budget_usd)
                    or existing.egress_allowlist != normalized_egress
                    or (session_id is not None and existing.session_id != session_id)
                ):
                    raise RuntimeStoreConflict("session binding mismatch")
                return existing

            if max_active_sessions is not None:
                if type(max_active_sessions) is not int or max_active_sessions <= 0:
                    raise ValueError("max_active_sessions must be positive")
                active = await (
                    await db.execute(
                        "SELECT COUNT(*) AS count FROM runtime_sessions WHERE state NOT IN "
                        "('completed', 'failed', 'cancelled', 'fenced', 'quarantined')"
                    )
                ).fetchone()
                if int(active["count"]) >= max_active_sessions:
                    raise RuntimeStoreBackpressure("runtime session capacity reached")

            new_session_id = session_id or f"ref-{uuid.uuid4().hex[:16]}"
            _require_text("session_id", new_session_id)
            await db.execute(
                "INSERT INTO runtime_sessions "
                "(session_id, run_id, client_run_id, epoch, scopes_json, budget_usd, "
                "egress_allowlist_json, state) VALUES (?, ?, ?, ?, ?, ?, ?, 'created')",
                (
                    new_session_id, run_id, client_run_id, epoch, scopes_json,
                    float(budget_usd), egress_json,
                ),
            )
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_sessions WHERE session_id = ?", (new_session_id,)
                )
            ).fetchone()
            return self._session(row)

    async def get_session(self, session_id: str) -> StoredSession | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
                )
            ).fetchone()
            return None if row is None else self._session(row)
        finally:
            await db.close()

    async def transition_session(
        self,
        session_id: str,
        *,
        expected_states: str | Iterable[str],
        new_state: str,
        checkpoint: Any = _UNSET,
    ) -> StoredSession:
        expected = {expected_states} if isinstance(expected_states, str) else set(expected_states)
        if not expected or not expected <= SESSION_STATES or new_state not in SESSION_STATES:
            raise ValueError("unknown session state")
        checkpoint_json = (
            None
            if checkpoint is _UNSET
            else canonical_json_bytes(
                checkpoint, max_bytes=MAX_UNACKED_BYTES
            ).decode("utf-8")
        )
        async with self._transaction() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
                )
            ).fetchone()
            if row is None:
                raise RuntimeStoreNotFound("session not found")
            if row["state"] not in expected:
                raise RuntimeStoreConflict(
                    f"session state {row['state']!r} is not one of {sorted(expected)!r}"
                )
            if checkpoint is _UNSET:
                await db.execute(
                    "UPDATE runtime_sessions SET state = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE session_id = ?",
                    (new_state, session_id),
                )
            else:
                await db.execute(
                    "UPDATE runtime_sessions SET state = ?, checkpoint_json = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                    (new_state, checkpoint_json, session_id),
                )
            updated = await (
                await db.execute(
                    "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
                )
            ).fetchone()
            return self._session(updated)

    @staticmethod
    def _event(row: aiosqlite.Row) -> StoredEvent:
        return StoredEvent(
            session_id=row["session_id"], cursor=row["cursor"], event_id=row["event_id"],
            event_kind=row["event_kind"], turn_id=row["turn_id"],
            intent_id=row["intent_id"], outcome=row["outcome"],
            tool_name=row["tool_name"], tool_args=_load(row["tool_args_json"]),
            tool_args_digest=row["tool_args_digest"],
            payload=_load(row["payload_json"]), dedupe_key=row["dedupe_key"],
            occurred_at=_stored_datetime(row["created_at"]),
        )

    async def append_event(
        self,
        session_id: str,
        *,
        event_kind: str,
        payload: Any,
        turn_id: str | None = None,
        intent_id: str | None = None,
        outcome: str | None = None,
        tool_name: str | None = None,
        tool_args: Any | None = None,
        tool_args_digest: str | None = None,
        encoded_size: int | None = None,
        event_id: str | None = None,
        dedupe_key: str | None = None,
    ) -> StoredEvent:
        _require_text("event_kind", event_kind)
        payload_json = _canonical_text(payload)
        tool_args_json = None if tool_args is None else _canonical_text(tool_args)
        content = {
            "event_kind": event_kind, "turn_id": turn_id, "intent_id": intent_id,
            "outcome": outcome, "tool_name": tool_name, "tool_args": tool_args,
            "tool_args_digest": tool_args_digest, "payload": payload,
        }
        event_bytes = (
            len(canonical_json_bytes(content, max_bytes=MAX_EVENT_BYTES))
            if encoded_size is None
            else encoded_size
        )
        if type(event_bytes) is not int or not 1 <= event_bytes <= MAX_EVENT_BYTES:
            raise ValueError("event encoded size is invalid")
        event_digest = _digest(content)
        async with self._transaction() as db:
            if dedupe_key is not None:
                existing = await (
                    await db.execute(
                        "SELECT * FROM runtime_events WHERE session_id = ? AND dedupe_key = ?",
                        (session_id, dedupe_key),
                    )
                ).fetchone()
                if existing is not None:
                    if existing["event_digest"] != event_digest:
                        raise RuntimeStoreConflict("event dedupe key payload mismatch")
                    return self._event(existing)
            session = await (
                await db.execute(
                    "SELECT next_event_cursor, acked_event_cursor FROM runtime_sessions "
                    "WHERE session_id = ?",
                    (session_id,),
                )
            ).fetchone()
            if session is None:
                raise RuntimeStoreNotFound("session not found")
            unacked_events = (
                session["next_event_cursor"] - 1 - session["acked_event_cursor"]
            )
            if unacked_events >= MAX_UNACKED_EVENTS:
                raise RuntimeStoreBackpressure("unacked event count limit reached")
            unacked_bytes = (
                await (
                    await db.execute(
                        "SELECT coalesce(sum(event_bytes), 0) "
                        "FROM runtime_events WHERE session_id = ? AND cursor > ?",
                        (session_id, session["acked_event_cursor"]),
                    )
                ).fetchone()
            )[0]
            if int(unacked_bytes) + event_bytes > MAX_UNACKED_BYTES:
                raise RuntimeStoreBackpressure("unacked event byte limit reached")
            cursor = session["next_event_cursor"]
            stored_event_id = event_id or str(uuid.uuid4())
            await db.execute(
                "INSERT INTO runtime_events "
                "(session_id, cursor, event_id, event_kind, turn_id, intent_id, outcome, "
                "tool_name, tool_args_json, tool_args_digest, payload_json, event_digest, "
                "event_bytes, dedupe_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id, cursor, stored_event_id, event_kind, turn_id, intent_id,
                    outcome, tool_name, tool_args_json, tool_args_digest, payload_json,
                    event_digest, event_bytes, dedupe_key,
                ),
            )
            await db.execute(
                "UPDATE runtime_sessions SET next_event_cursor = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE session_id = ?",
                (cursor + 1, session_id),
            )
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_events WHERE session_id = ? AND cursor = ?",
                    (session_id, cursor),
                )
            ).fetchone()
            return self._event(row)

    async def acknowledge_events(self, session_id: str, *, cursor: int) -> StoredSession:
        if type(cursor) is not int or cursor < 0:
            raise ValueError("event ACK cursor must be non-negative")
        async with self._transaction() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
                )
            ).fetchone()
            if row is None:
                raise RuntimeStoreNotFound("session not found")
            latest = row["next_event_cursor"] - 1
            if cursor > latest:
                raise RuntimeStoreConflict("event ACK exceeds emitted cursor")
            if cursor < row["acked_event_cursor"]:
                raise RuntimeStoreConflict("event ACK cursor regressed")
            await db.execute(
                "UPDATE runtime_sessions SET acked_event_cursor = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (cursor, session_id),
            )
            updated = await (
                await db.execute(
                    "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
                )
            ).fetchone()
            return self._session(updated)

    async def list_events(
        self, session_id: str, *, after: int = 0, limit: int = 1000
    ) -> list[StoredEvent]:
        if (
            type(after) is not int
            or type(limit) is not int
            or after < 0
            or not 1 <= limit <= 1000
        ):
            raise ValueError("invalid event replay window")
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    "SELECT * FROM runtime_events WHERE session_id = ? AND cursor > ? "
                    "ORDER BY cursor LIMIT ?",
                    (session_id, after, limit),
                )
            ).fetchall()
            return [self._event(row) for row in rows]
        finally:
            await db.close()

    @staticmethod
    def _intent(row: aiosqlite.Row) -> StoredIntent:
        return StoredIntent(
            session_id=row["session_id"], turn_id=row["turn_id"],
            intent_id=row["intent_id"], tool=row["tool"], args=_load(row["args_json"]),
            state=row["state"], result_digest=row["result_digest"],
            result_outcome=row["result_outcome"],
            result_payload=_load(row["result_payload_json"]),
            result_command_id=row["result_command_id"],
            result_action_id=row["result_action_id"],
        )

    async def record_intent(
        self, session_id: str, *, turn_id: str, intent_id: str, tool: str, args: Any
    ) -> StoredIntent:
        for name, value in (("turn_id", turn_id), ("intent_id", intent_id), ("tool", tool)):
            _require_text(name, value)
        args_json = _canonical_text(args)
        async with self._transaction() as db:
            existing = await (
                await db.execute(
                    "SELECT * FROM runtime_intents WHERE session_id = ? AND intent_id = ?",
                    (session_id, intent_id),
                )
            ).fetchone()
            if existing is not None:
                value = self._intent(existing)
                if value.turn_id != turn_id or value.tool != tool or value.args != args:
                    raise RuntimeStoreConflict("intent binding mismatch")
                return value
            try:
                await db.execute(
                    "INSERT INTO runtime_intents "
                    "(session_id, turn_id, intent_id, tool, args_json, state) "
                    "VALUES (?, ?, ?, ?, ?, 'pending')",
                    (session_id, turn_id, intent_id, tool, args_json),
                )
            except aiosqlite.IntegrityError as exc:
                raise RuntimeStoreConflict("session already has a pending intent or turn") from exc
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_intents WHERE session_id = ? AND intent_id = ?",
                    (session_id, intent_id),
                )
            ).fetchone()
            return self._intent(row)

    async def get_intent(self, session_id: str, intent_id: str) -> StoredIntent | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_intents WHERE session_id = ? AND intent_id = ?",
                    (session_id, intent_id),
                )
            ).fetchone()
            return None if row is None else self._intent(row)
        finally:
            await db.close()

    async def count_active_intents(self, session_id: str) -> int:
        """Return intents that still block final/artifact publication."""

        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT count(*) FROM runtime_intents "
                    "WHERE session_id = ? AND state IN ('pending', 'result_recorded')",
                    (session_id,),
                )
            ).fetchone()
            return int(row[0])
        finally:
            await db.close()

    async def resolve_intent(
        self,
        session_id: str,
        *,
        intent_id: str,
        result_digest: str,
        outcome: str,
        payload: Any,
        turn_id: str | None = None,
        command_id: str | None = None,
        action_id: str | None = None,
        stored_payload: Any = _UNSET,
    ) -> StoredIntent:
        if not _DIGEST_RE.fullmatch(result_digest):
            raise ValueError("result_digest must be lowercase sha256")
        if outcome not in RESULT_OUTCOMES:
            raise ValueError("unknown result outcome")
        if _digest(payload) != result_digest:
            raise RuntimeStoreConflict("result digest does not match payload")
        value_to_store = payload if stored_payload is _UNSET else stored_payload
        payload_json = _canonical_text(value_to_store)
        for name, value in (
            ("turn_id", turn_id),
            ("command_id", command_id),
            ("action_id", action_id),
        ):
            if value is not None:
                _require_text(name, value)
        async with self._transaction() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_intents WHERE session_id = ? AND intent_id = ?",
                    (session_id, intent_id),
                )
            ).fetchone()
            if row is None:
                raise RuntimeStoreNotFound("intent not found")
            existing = self._intent(row)
            if turn_id is not None and existing.turn_id != turn_id:
                raise RuntimeStoreConflict("result turn binding mismatch")
            if existing.state != "pending":
                if (
                    existing.result_digest == result_digest
                    and existing.result_outcome == outcome
                    and existing.result_payload == value_to_store
                    and existing.result_command_id == command_id
                    and existing.result_action_id == action_id
                ):
                    return existing
                raise RuntimeStoreConflict("intent already has a different result")
            await db.execute(
                "UPDATE runtime_intents SET state = 'result_recorded', result_digest = ?, "
                "result_outcome = ?, result_payload_json = ?, result_command_id = ?, "
                "result_action_id = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE session_id = ? AND intent_id = ?",
                (
                    result_digest, outcome, payload_json, command_id, action_id,
                    session_id, intent_id,
                ),
            )
            updated = await (
                await db.execute(
                    "SELECT * FROM runtime_intents WHERE session_id = ? AND intent_id = ?",
                    (session_id, intent_id),
                )
            ).fetchone()
            return self._intent(updated)

    async def mark_intent_applied(self, session_id: str, intent_id: str) -> StoredIntent:
        async with self._transaction() as db:
            cursor = await db.execute(
                "UPDATE runtime_intents SET state = 'applied', updated_at = CURRENT_TIMESTAMP "
                "WHERE session_id = ? AND intent_id = ? AND state = 'result_recorded'",
                (session_id, intent_id),
            )
            if cursor.rowcount != 1:
                row = await (
                    await db.execute(
                        "SELECT * FROM runtime_intents WHERE session_id = ? AND intent_id = ?",
                        (session_id, intent_id),
                    )
                ).fetchone()
                if row is None:
                    raise RuntimeStoreNotFound("intent not found")
                if row["state"] != "applied":
                    raise RuntimeStoreConflict("intent result is not recorded")
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_intents WHERE session_id = ? AND intent_id = ?",
                    (session_id, intent_id),
                )
            ).fetchone()
            return self._intent(row)

    @staticmethod
    def _artifact(row: aiosqlite.Row) -> StoredArtifact:
        return StoredArtifact(
            session_id=row["session_id"], artifact_id=row["artifact_id"],
            kind=row["kind"], title=row["title"], uri=row["uri"],
            text_md=row["text_md"], meta=_load(row["meta_json"]),
            artifact_digest=row["artifact_digest"],
            content_type=row["content_type"],
            original_filename=row["original_filename"],
            declared_byte_size=row["declared_byte_size"],
            expected_sha256=row["expected_sha256"],
            required=bool(row["required"]),
            producer_action_id=row["producer_action_id"],
            spool_locator=row["spool_locator"],
            upload_state=row["upload_state"],
            upload_command=_load(row["upload_command_json"]),
            upload_command_digest=row["upload_command_digest"],
            upload_id=row["upload_id"],
            upload_receipt=_load(row["upload_receipt_json"]),
            upload_receipt_digest=row["upload_receipt_digest"],
            upload_attempts=row["upload_attempts"],
            last_upload_error=row["last_upload_error"],
            upload_acked_at=(
                None
                if row["upload_acked_at"] is None
                else _stored_datetime(row["upload_acked_at"])
            ),
            spool_deleted_at=(
                None
                if row["spool_deleted_at"] is None
                else _stored_datetime(row["spool_deleted_at"])
            ),
        )

    async def put_artifact(
        self,
        session_id: str,
        *,
        artifact_id: str,
        kind: str,
        title: str,
        uri: str | None = None,
        text_md: str | None = None,
        meta: Any | None = None,
        content_type: str | None = None,
        original_filename: str | None = None,
        required: bool = True,
        producer_action_id: str | None = None,
    ) -> StoredArtifact:
        if uri is not None:
            raise ValueError("protocol-v2 runtime artifacts cannot retain external URIs")
        if not isinstance(text_md, str):
            raise ValueError("protocol-v2 runtime artifact bytes are required")
        content = text_md.encode("utf-8")
        return await self.put_artifact_bytes(
            session_id,
            artifact_id=artifact_id,
            kind=kind,
            title=title,
            content=content,
            meta=meta,
            content_type=content_type or (
                "text/markdown; charset=utf-8"
                if kind == "text"
                else "text/plain; charset=utf-8"
            ),
            original_filename=original_filename,
            declared_byte_size=len(content),
            expected_sha256=hashlib.sha256(content).hexdigest(),
            required=required,
            producer_action_id=producer_action_id,
        )

    @staticmethod
    def artifact_declaration(
        *,
        artifact_id: str,
        kind: str,
        title: str,
        content_type: str,
        original_filename: str | None,
        declared_byte_size: int,
        expected_sha256: str,
        required: bool,
        producer_action_id: str | None,
        meta: Any,
    ) -> tuple[dict[str, Any], str]:
        for name, value, maximum in (
            ("artifact_id", artifact_id, 200),
            ("title", title, 200),
            ("content_type", content_type, 200),
        ):
            _require_text(name, value)
            if len(value) > maximum or value != value.strip() or any(
                ord(char) < 32 for char in value
            ):
                raise ValueError(f"{name} is not canonical")
        if kind not in {"file", "link", "text", "image", "dataset"}:
            raise ValueError("unknown artifact kind")
        if kind == "link" and required:
            raise ValueError("required runtime artifacts must contain snapshotted bytes")
        if type(required) is not bool:
            raise ValueError("artifact required must be boolean")
        if (
            type(declared_byte_size) is not int
            or declared_byte_size < 0
        ):
            raise ValueError("declared_byte_size must be non-negative")
        if not _DIGEST_RE.fullmatch(expected_sha256):
            raise ValueError("expected_sha256 must be lowercase sha256")
        if producer_action_id is not None:
            _require_text("producer_action_id", producer_action_id)
            if len(producer_action_id) > 200:
                raise ValueError("producer_action_id is too long")
        if original_filename is not None:
            _require_text("original_filename", original_filename)
            if (
                len(original_filename) > 255
                or original_filename in {".", ".."}
                or "/" in original_filename
                or "\\" in original_filename
                or original_filename != original_filename.strip()
                or any(ord(char) < 32 for char in original_filename)
            ):
                raise ValueError("original_filename must not contain a path")
        elif kind != "text":
            raise ValueError("binary artifact original_filename is required")
        meta_value = {} if meta is None else meta
        _canonical_text(meta_value)
        declaration = {
            "kind": kind,
            "title": title,
            "content_type": content_type,
            "original_filename": original_filename,
            "declared_byte_size": declared_byte_size,
            "expected_sha256": expected_sha256,
            "required": required,
            "producer_action_id": producer_action_id,
            "meta": meta_value,
        }
        return declaration, _digest(declaration)

    async def stage_artifact_bytes(
        self,
        session_id: str,
        artifact_id: str,
        *,
        content: bytes,
        declared_byte_size: int,
        expected_sha256: str,
    ) -> SpooledArtifact:
        _require_text("session_id", session_id)
        _require_text("artifact_id", artifact_id)
        if not isinstance(content, bytes):
            raise TypeError("runtime artifact content must be bytes")
        actual_size = len(content)
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if (
            type(declared_byte_size) is not int
            or declared_byte_size != actual_size
            or expected_sha256 != actual_sha256
        ):
            raise RuntimeStoreConflict("artifact byte declaration mismatch")
        if await self.get_session(session_id) is None:
            raise RuntimeStoreNotFound("session not found")
        try:
            return await self.artifact_spool.put(
                session_id, artifact_id, content
            )
        except ArtifactSpoolError as exc:
            raise RuntimeStoreBackpressure(
                "runtime artifact spool unavailable"
            ) from exc

    async def put_artifact_bytes(
        self,
        session_id: str,
        *,
        artifact_id: str,
        kind: str,
        title: str,
        content: bytes,
        content_type: str,
        original_filename: str | None,
        declared_byte_size: int,
        expected_sha256: str,
        meta: Any | None = None,
        required: bool = True,
        producer_action_id: str | None = None,
    ) -> StoredArtifact:
        if not isinstance(content, bytes):
            raise TypeError("runtime artifact content must be bytes")
        declaration, artifact_digest = self.artifact_declaration(
            artifact_id=artifact_id,
            kind=kind,
            title=title,
            content_type=content_type,
            original_filename=original_filename,
            declared_byte_size=declared_byte_size,
            expected_sha256=expected_sha256,
            required=required,
            producer_action_id=producer_action_id,
            meta=meta,
        )
        if (
            len(content) != declared_byte_size
            or hashlib.sha256(content).hexdigest() != expected_sha256
        ):
            raise RuntimeStoreConflict("artifact byte declaration mismatch")
        existing = await self.get_artifact(session_id, artifact_id)
        if existing is not None:
            if existing.artifact_digest != artifact_digest:
                raise RuntimeStoreConflict("artifact id payload mismatch")
            return existing
        spooled = await self.stage_artifact_bytes(
            session_id,
            artifact_id,
            content=content,
            declared_byte_size=declared_byte_size,
            expected_sha256=expected_sha256,
        )
        return await self.put_artifact_from_spool(
            session_id,
            artifact_id=artifact_id,
            kind=kind,
            title=title,
            spool_locator=spooled.locator,
            content_type=content_type,
            original_filename=original_filename,
            declared_byte_size=declared_byte_size,
            expected_sha256=expected_sha256,
            meta=meta,
            required=required,
            producer_action_id=producer_action_id,
        )

    async def put_artifact_from_spool(
        self,
        session_id: str,
        *,
        artifact_id: str,
        kind: str,
        title: str,
        spool_locator: str,
        content_type: str,
        original_filename: str | None,
        declared_byte_size: int,
        expected_sha256: str,
        meta: Any | None = None,
        required: bool = True,
        producer_action_id: str | None = None,
    ) -> StoredArtifact:
        declaration, artifact_digest = self.artifact_declaration(
            artifact_id=artifact_id,
            kind=kind,
            title=title,
            content_type=content_type,
            original_filename=original_filename,
            declared_byte_size=declared_byte_size,
            expected_sha256=expected_sha256,
            required=required,
            producer_action_id=producer_action_id,
            meta=meta,
        )
        if spool_locator != self.artifact_spool.locator_for(
            session_id, artifact_id
        ):
            raise RuntimeStoreConflict("artifact spool binding mismatch")
        async with self._artifact_lock:
            existing = await self.get_artifact(session_id, artifact_id)
            if existing is not None:
                if existing.artifact_digest != artifact_digest:
                    raise RuntimeStoreConflict("artifact id payload mismatch")
                return existing
            try:
                spooled = await self.artifact_spool.digest(spool_locator)
            except ArtifactSpoolError as exc:
                raise RuntimeStoreConflict("artifact spool entry is unavailable") from exc
            if (
                spooled.byte_size != declared_byte_size
                or spooled.sha256 != expected_sha256
            ):
                raise RuntimeStoreConflict("artifact spool declaration mismatch")
            meta_json = _canonical_text(declaration["meta"])
            async with self._transaction() as db:
                await db.execute(
                    "INSERT INTO runtime_artifacts "
                    "(session_id, artifact_id, kind, title, uri, text_md, meta_json, "
                    "artifact_digest, content_type, original_filename, declared_byte_size, "
                    "expected_sha256, required, producer_action_id, spool_locator, upload_state) "
                    "VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
                    (
                        session_id,
                        artifact_id,
                        kind,
                        title,
                        meta_json,
                        artifact_digest,
                        content_type,
                        original_filename,
                        spooled.byte_size,
                        spooled.sha256,
                        int(required),
                        producer_action_id,
                        spooled.locator,
                    ),
                )
                row = await (
                    await db.execute(
                        "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                        (session_id, artifact_id),
                    )
                ).fetchone()
                return self._artifact(row)

    async def get_artifact(
        self, session_id: str, artifact_id: str
    ) -> StoredArtifact | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            return None if row is None else self._artifact(row)
        finally:
            await db.close()

    async def list_artifacts(self, session_id: str) -> list[StoredArtifact]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? "
                    "ORDER BY created_at, artifact_id",
                    (session_id,),
                )
            ).fetchall()
            return [self._artifact(row) for row in rows]
        finally:
            await db.close()

    async def claim_artifact_upload(
        self,
        session_id: str,
        artifact_id: str,
        *,
        upload_id: str,
        command: Any,
        command_digest: str,
    ) -> StoredArtifact:
        _require_text("upload_id", upload_id)
        if not _DIGEST_RE.fullmatch(command_digest):
            raise ValueError("upload command digest must be lowercase sha256")
        command_json = _canonical_text(command)
        async with self._transaction() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            if row is None:
                raise RuntimeStoreNotFound("artifact not found")
            artifact = self._artifact(row)
            if artifact.upload_state in {"legacy_inline", "acknowledged"}:
                raise RuntimeStoreConflict("artifact does not accept upload commands")
            if artifact.upload_receipt_digest is not None:
                if (
                    artifact.upload_id != upload_id
                    or artifact.upload_command_digest != command_digest
                ):
                    raise RuntimeStoreConflict("artifact upload already completed")
                return artifact
            if artifact.upload_command_digest is not None:
                if artifact.upload_command_digest == command_digest:
                    if artifact.upload_id != upload_id:
                        raise RuntimeStoreConflict("artifact upload id changed")
                elif artifact.upload_id == upload_id:
                    raise RuntimeStoreConflict("artifact upload command payload changed")
            await db.execute(
                "UPDATE runtime_artifacts SET upload_state = 'uploading', "
                "upload_command_json = ?, upload_command_digest = ?, upload_id = ?, "
                "upload_attempts = upload_attempts + 1, last_upload_error = NULL "
                "WHERE session_id = ? AND artifact_id = ?",
                (
                    command_json,
                    command_digest,
                    upload_id,
                    session_id,
                    artifact_id,
                ),
            )
            updated = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            return self._artifact(updated)

    async def record_artifact_upload(
        self,
        session_id: str,
        artifact_id: str,
        *,
        upload_id: str,
        command_digest: str,
        receipt: Any,
        receipt_digest: str,
        succeeded: bool,
        error_code: str | None,
    ) -> StoredArtifact:
        if not _DIGEST_RE.fullmatch(receipt_digest):
            raise ValueError("upload receipt digest must be lowercase sha256")
        if succeeded == bool(error_code):
            raise ValueError("upload receipt outcome is inconsistent")
        receipt_json = _canonical_text(receipt)
        async with self._transaction() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            if row is None:
                raise RuntimeStoreNotFound("artifact not found")
            artifact = self._artifact(row)
            if (
                artifact.upload_id != upload_id
                or artifact.upload_command_digest != command_digest
            ):
                raise RuntimeStoreConflict("artifact upload binding changed")
            if artifact.upload_receipt_digest is not None:
                if (
                    artifact.upload_receipt_digest != receipt_digest
                    or artifact.upload_receipt != receipt
                ):
                    raise RuntimeStoreConflict("artifact upload receipt changed")
                return artifact
            await db.execute(
                "UPDATE runtime_artifacts SET upload_state = ?, "
                "upload_receipt_json = ?, upload_receipt_digest = ?, "
                "last_upload_error = ? WHERE session_id = ? AND artifact_id = ?",
                (
                    "uploaded" if succeeded else "failed",
                    receipt_json,
                    receipt_digest,
                    None if succeeded else error_code[:100],
                    session_id,
                    artifact_id,
                ),
            )
            updated = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            return self._artifact(updated)

    async def record_artifact_upload_failure(
        self, session_id: str, artifact_id: str, *, error_code: str
    ) -> StoredArtifact:
        _require_text("error_code", error_code)
        async with self._transaction() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            if row is None:
                raise RuntimeStoreNotFound("artifact not found")
            if row["upload_receipt_digest"] is None:
                await db.execute(
                    "UPDATE runtime_artifacts SET upload_state = 'failed', "
                    "last_upload_error = ? WHERE session_id = ? AND artifact_id = ?",
                    (error_code[:100], session_id, artifact_id),
                )
            updated = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            return self._artifact(updated)

    async def acknowledge_artifact_upload(
        self,
        session_id: str,
        artifact_id: str,
        *,
        receipt_digest: str,
    ) -> StoredArtifact:
        if not _DIGEST_RE.fullmatch(receipt_digest):
            raise ValueError("upload receipt digest must be lowercase sha256")
        async with self._transaction() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            if row is None:
                raise RuntimeStoreNotFound("artifact not found")
            artifact = self._artifact(row)
            if artifact.upload_receipt_digest != receipt_digest:
                raise RuntimeStoreConflict("artifact upload ACK receipt mismatch")
            if artifact.upload_state not in {"uploaded", "acknowledged", "failed"}:
                raise RuntimeStoreConflict("artifact upload is not ready for ACK")
            if artifact.upload_state == "uploaded":
                await db.execute(
                    "UPDATE runtime_artifacts SET upload_state = 'acknowledged', "
                    "upload_acked_at = CURRENT_TIMESTAMP "
                    "WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            elif artifact.upload_acked_at is None:
                await db.execute(
                    "UPDATE runtime_artifacts SET upload_acked_at = CURRENT_TIMESTAMP "
                    "WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            updated = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            return self._artifact(updated)

    async def mark_artifact_spool_deleted(
        self, session_id: str, artifact_id: str
    ) -> StoredArtifact:
        async with self._transaction() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            if row is None:
                raise RuntimeStoreNotFound("artifact not found")
            if row["upload_acked_at"] is None:
                raise RuntimeStoreConflict("artifact spool cannot be deleted before ACK")
            await db.execute(
                "UPDATE runtime_artifacts SET spool_deleted_at = COALESCE("
                "spool_deleted_at, CURRENT_TIMESTAMP) "
                "WHERE session_id = ? AND artifact_id = ?",
                (session_id, artifact_id),
            )
            updated = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE session_id = ? AND artifact_id = ?",
                    (session_id, artifact_id),
                )
            ).fetchone()
            return self._artifact(updated)

    async def list_recoverable_artifact_uploads(self) -> list[StoredArtifact]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE (upload_state = 'uploading' "
                    "OR (upload_state = 'failed' AND last_upload_error IN "
                    "('upload_transport_failed', 'upload_ingest_unavailable'))) "
                    "AND upload_command_json IS NOT NULL "
                    "ORDER BY created_at, artifact_id"
                )
            ).fetchall()
            return [self._artifact(row) for row in rows]
        finally:
            await db.close()

    async def list_acked_artifact_spools(self) -> list[StoredArtifact]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    "SELECT * FROM runtime_artifacts WHERE upload_acked_at IS NOT NULL "
                    "AND upload_receipt_digest IS NOT NULL "
                    "AND spool_locator IS NOT NULL AND spool_deleted_at IS NULL "
                    "ORDER BY created_at, artifact_id"
                )
            ).fetchall()
            return [self._artifact(row) for row in rows]
        finally:
            await db.close()

    async def readiness(self) -> dict[str, int]:
        async with self._transaction() as db:
            await db.execute(
                "INSERT INTO runtime_health(singleton, checked_at) VALUES (1, ?) "
                "ON CONFLICT(singleton) DO UPDATE SET checked_at = excluded.checked_at",
                (datetime.now(UTC).isoformat(),),
            )
            row = await (
                await db.execute(
                    "SELECT COUNT(*) AS active_sessions FROM runtime_sessions "
                    "WHERE state NOT IN ('completed', 'failed', 'cancelled', 'fenced', 'quarantined')"
                )
            ).fetchone()
        return {
            "active_sessions": int(row["active_sessions"]),
            "spool_bytes": await self.artifact_spool.size(),
        }

    @staticmethod
    def _command(row: aiosqlite.Row) -> StoredCommandReceipt:
        binding = CommandBinding(
            audience=row["audience"], command_id=row["command_id"], jti=row["jti"],
            request_digest=row["request_digest"], run_id=row["run_id"],
            session_id=row["session_id"], epoch=row["epoch"], action=row["action"],
        )
        return StoredCommandReceipt(
            receipt_id=row["receipt_id"], binding=binding, state=row["state"],
            response=_load(row["response_json"]),
        )

    @staticmethod
    def _validate_binding(binding: CommandBinding) -> None:
        for name in (
            "audience", "command_id", "jti", "run_id", "session_id", "action",
        ):
            _require_text(name, getattr(binding, name))
        if type(binding.epoch) is not int or binding.epoch < 0:
            raise ValueError("epoch must be non-negative")
        if not _DIGEST_RE.fullmatch(binding.request_digest):
            raise ValueError("request_digest must be lowercase sha256")

    async def inspect_command(
        self, binding: CommandBinding
    ) -> StoredCommandReceipt | None:
        """Reject a known cross-binding before any session existence lookup."""

        self._validate_binding(binding)
        db = await self._connect()
        try:
            by_jti = await (
                await db.execute(
                    "SELECT * FROM runtime_command_receipts WHERE jti = ?",
                    (binding.jti,),
                )
            ).fetchone()
            by_command = await (
                await db.execute(
                    "SELECT * FROM runtime_command_receipts "
                    "WHERE audience = ? AND command_id = ?",
                    (binding.audience, binding.command_id),
                )
            ).fetchone()
            existing_rows = [row for row in (by_jti, by_command) if row is not None]
            if not existing_rows:
                return None
            if any(self._command(row).binding != binding for row in existing_rows):
                raise CrossBindingReplay("command token binding mismatch")
            return self._command(existing_rows[0])
        finally:
            await db.close()

    async def claim_command(self, binding: CommandBinding) -> CommandClaim:
        """Persist the first binding or return its exact durable retry receipt."""

        self._validate_binding(binding)
        async with self._transaction() as db:
            by_jti = await (
                await db.execute(
                    "SELECT * FROM runtime_command_receipts WHERE jti = ?", (binding.jti,)
                )
            ).fetchone()
            by_command = await (
                await db.execute(
                    "SELECT * FROM runtime_command_receipts "
                    "WHERE audience = ? AND command_id = ?",
                    (binding.audience, binding.command_id),
                )
            ).fetchone()
            existing_rows = [row for row in (by_jti, by_command) if row is not None]
            if existing_rows:
                if any(self._command(row).binding != binding for row in existing_rows):
                    raise CrossBindingReplay("command token binding mismatch")
                receipt = self._command(existing_rows[0])
                return CommandClaim(receipt=receipt, is_retry=True)

            receipt_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO runtime_command_receipts "
                "(jti, audience, command_id, request_digest, run_id, session_id, epoch, "
                "action, receipt_id, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted')",
                (
                    binding.jti, binding.audience, binding.command_id,
                    binding.request_digest, binding.run_id, binding.session_id,
                    binding.epoch, binding.action, receipt_id,
                ),
            )
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_command_receipts WHERE jti = ?", (binding.jti,)
                )
            ).fetchone()
            return CommandClaim(receipt=self._command(row), is_retry=False)

    async def complete_command(
        self, binding: CommandBinding, *, response: Any
    ) -> StoredCommandReceipt:
        self._validate_binding(binding)
        response_json = _canonical_text(response)
        async with self._transaction() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_command_receipts WHERE jti = ?", (binding.jti,)
                )
            ).fetchone()
            if row is None:
                raise RuntimeStoreNotFound("command receipt not found")
            existing = self._command(row)
            if existing.binding != binding:
                raise CrossBindingReplay("command token binding mismatch")
            if isinstance(response, dict):
                if response.get("receipt_id", existing.receipt_id) != existing.receipt_id:
                    raise RuntimeStoreConflict("response receipt_id mismatch")
                if (
                    response.get("request_digest", binding.request_digest)
                    != binding.request_digest
                ):
                    raise RuntimeStoreConflict("response request_digest mismatch")
            if existing.state == "completed":
                if existing.response != response:
                    raise RuntimeStoreConflict("completed command response mismatch")
                return existing
            await db.execute(
                "UPDATE runtime_command_receipts SET state = 'completed', response_json = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE jti = ?",
                (response_json, binding.jti),
            )
            updated = await (
                await db.execute(
                    "SELECT * FROM runtime_command_receipts WHERE jti = ?", (binding.jti,)
                )
            ).fetchone()
            return self._command(updated)

    async def get_command(self, jti: str) -> StoredCommandReceipt | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT * FROM runtime_command_receipts WHERE jti = ?", (jti,)
                )
            ).fetchone()
            return None if row is None else self._command(row)
        finally:
            await db.close()
