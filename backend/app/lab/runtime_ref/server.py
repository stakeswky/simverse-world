"""Simverse reference runtime — standalone HTTP server (recovery plan Phase 7).

A real, self-hosted agent runtime speaking the Lab HTTP wire protocol
(``HttpAgentAdapter`` in ``app/lab/sandbox/base.py``). It drives the real
``RefAgent`` loop against the project's Anthropic-compatible LLM endpoint and
streams protocol steps back to the Gateway. It holds NO DB/Redis/world handle —
its only outbound credential is the model endpoint — and it only INTENDS tool
calls; the Gateway's Broker mediates every effect.

Run standalone only with an explicit ``LAB_RUNTIME_PROTOCOL_VERSION`` and the
corresponding isolated Runtime configuration. The process fails closed when
that configuration is absent or incomplete.
The Gateway's ``SimverseRefAdapter`` points at this via
``settings.lab_simverse_ref_base_url``.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Mapping

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.lab import guard
from app.lab.protocol import (
    MAX_COMMAND_BYTES,
    MAX_EVENT_BYTES,
    MAX_UNACKED_BYTES,
    MAX_UNACKED_EVENTS,
    RuntimeArtifactManifest,
    RuntimeArtifactUploadAck,
    RuntimeArtifactUploadCommand,
    ControlCommand,
    RuntimeEvent,
    RuntimeV2Handshake,
    ToolResultCommand,
    args_digest,
    runtime_v2_supervision_handshake,
)
from app.lab.runtime_ref.agent import AgentTurn, RefAgent, anthropic_completer
from app.lab.runtime_ref.service_auth import (
    MAX_REQUEST_BYTES,
    RequestSchemaError,
    ServiceAuthConfig,
    ServiceAuthError,
    ServiceBinding,
    ServiceClaims,
    ServiceTokenValidator,
    StrictRequestModel,
    canonical_json_bytes,
    canonical_request_digest,
    extract_bearer_token,
)
from app.lab.runtime_ref.store import (
    CommandBinding,
    CrossBindingReplay,
    RuntimeStore,
    RuntimeStoreBackpressure,
    RuntimeStoreConflict,
    RuntimeStoreNotFound,
    StoredSession,
)
from app.lab.runtime_ref.spool import ArtifactSpoolError
from app.lab.runtime_ref.uploader import ArtifactUploader, ArtifactUploadError


_RUNTIME_LOOP_VERSION = 1
_MAX_RUNTIME_JSON_DEPTH = 32


class _RuntimeWorkBackpressure(RuntimeError):
    pass


class _RuntimeWorkAdmission:
    def __init__(self, *, max_concurrent: int, max_queue_depth: int) -> None:
        if type(max_concurrent) is not int or max_concurrent <= 0:
            raise ValueError("max_concurrent_turns must be positive")
        if type(max_queue_depth) is not int or max_queue_depth < 0:
            raise ValueError("max_queue_depth must be non-negative")
        self.max_concurrent = max_concurrent
        self.max_queue_depth = max_queue_depth
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._state_lock = asyncio.Lock()
        self._running = 0
        self._waiting = 0

    @asynccontextmanager
    async def slot(self):
        queued = False
        reserved = False
        async with self._state_lock:
            if self._running < self.max_concurrent:
                self._running += 1
                reserved = True
            else:
                if self._waiting >= self.max_queue_depth:
                    raise _RuntimeWorkBackpressure("runtime model queue is full")
                self._waiting += 1
                queued = True
        try:
            await self._semaphore.acquire()
        except BaseException:
            async with self._state_lock:
                if queued:
                    self._waiting -= 1
                if reserved:
                    self._running -= 1
            raise
        if queued:
            async with self._state_lock:
                self._waiting -= 1
                self._running += 1
        try:
            yield
        finally:
            async with self._state_lock:
                self._running -= 1
            self._semaphore.release()

    async def status(self) -> dict[str, int]:
        async with self._state_lock:
            return {"running_turns": self._running, "queue_depth": self._waiting}


@dataclass
class _Session:
    session_id: str
    scopes: list[str]
    steps: list[dict] = field(default_factory=list)   # protocol step dicts with seq
    artifacts: list[dict] = field(default_factory=list)
    done: bool = False
    cancelled: bool = False
    task: asyncio.Task | None = None


_SESSIONS: dict[str, _Session] = {}


class StartBody(BaseModel):
    run_id: str
    scopes: list[str] = []
    budget_usd: float = 0.5
    egress_allowlist: list[str] = []


class GoalBody(BaseModel):
    brief: str
    scopes: list[str] = []


class ApproveBody(BaseModel):
    approval_id: str
    decision: bool


class V2StartBody(StrictRequestModel):
    schema_version: Literal[2]
    command_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    client_run_id: str = Field(min_length=1, max_length=200)
    epoch: int = Field(ge=0)
    scopes: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list
    )
    budget_usd: float = Field(ge=0, allow_inf_nan=False)
    egress_allowlist: list[
        Annotated[str, Field(min_length=1, max_length=500)]
    ] = Field(default_factory=list)


class V2GoalBody(StrictRequestModel):
    schema_version: Literal[2]
    command_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    epoch: int = Field(ge=0)
    brief: str = Field(min_length=1)
    scopes: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list
    )


class V2ApproveBody(StrictRequestModel):
    schema_version: Literal[2]
    command_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    epoch: int = Field(ge=0)
    approval_id: str = Field(min_length=1, max_length=200)
    decision: bool


class V2EventAckBody(StrictRequestModel):
    schema_version: Literal[2]
    command_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    epoch: int = Field(ge=0)
    cursor: int = Field(ge=0)


def _completer():
    from app.llm.client import get_client
    return anthropic_completer(get_client("system"), settings.llm_model)


def _create_v1_app(completer_factory, max_steps: int) -> FastAPI:
    app = FastAPI(title="Simverse Lab reference runtime", version="1.0")

    def _sess(sid: str) -> _Session:
        s = _SESSIONS.get(sid)
        if s is None:
            raise HTTPException(status_code=404, detail="session not found")
        return s

    @app.post("/runs")
    async def start_run(body: StartBody):
        sid = f"ref-{uuid.uuid4().hex[:12]}"
        _SESSIONS[sid] = _Session(session_id=sid, scopes=list(body.scopes))
        return {"session_id": sid}

    @app.post("/runs/{sid}/goal")
    async def submit_goal(sid: str, body: GoalBody):
        s = _sess(sid)
        scopes = body.scopes or s.scopes

        def on_step(step) -> None:
            seq = len(s.steps) + 1
            s.steps.append({
                "seq": seq, "phase": step.phase, "tool": step.tool,
                "summary": step.summary, "payload": step.payload,
                "model_tokens": step.model_tokens, "approval": step.approval,
            })

        # Run the loop to completion here (buffering steps via on_step), so the
        # Gateway's subsequent /steps poll gets every step + done in one shot. This
        # is robust across transports (a fire-and-forget background task is not
        # reliably driven by every ASGI server / test transport). Incremental live
        # streaming during a long run is a noted follow-up; the poll-with-cursor
        # protocol contract holds either way.
        agent = RefAgent(complete=completer_factory(), max_steps=max_steps)
        result = await agent.run(brief=body.brief, scopes=scopes,
                                 on_step=on_step, should_cancel=lambda: s.cancelled)
        s.artifacts = [
            {"kind": a.kind, "title": a.title, "uri": a.uri, "text_md": a.text_md, "meta": a.meta}
            for a in result.artifacts]
        s.done = True
        return {"ok": True}

    @app.get("/runs/{sid}/steps")
    async def get_steps(sid: str, after: int = 0):
        s = _sess(sid)
        fresh = [st for st in s.steps if st["seq"] > after]
        return {"steps": fresh, "done": s.done or s.cancelled}

    @app.post("/runs/{sid}/approve")
    async def approve(sid: str, body: ApproveBody):
        _sess(sid)
        return {"ok": True}

    @app.get("/runs/{sid}/artifacts")
    async def artifacts(sid: str):
        s = _sess(sid)
        return {"artifacts": s.artifacts}

    async def _teardown(s: _Session) -> None:
        s.cancelled = True
        if s.task is not None and not s.task.done():
            s.task.cancel()

    @app.post("/runs/{sid}/stop")
    async def stop(sid: str):
        await _teardown(_sess(sid))
        return {"ok": True}

    @app.post("/runs/{sid}/cancel")
    async def cancel(sid: str):
        await _teardown(_sess(sid))
        return {"ok": True}

    @app.post("/runs/{sid}/terminate")
    async def terminate(sid: str):
        await _teardown(_sess(sid))
        return {"ok": True}

    @app.post("/runs/{sid}/kill")
    async def kill(sid: str):
        await _teardown(_sess(sid))
        return {"ok": True}

    @app.get("/runs/{sid}/health")
    async def health(sid: str):
        s = _sess(sid)
        alive = not (s.done or s.cancelled)
        return {"alive": alive, "cancelled": s.cancelled}

    return app


def _create_v2_app(
    *,
    completer_factory,
    max_steps: int,
    runtime_store_path: str,
    service_auth: ServiceAuthConfig | Mapping[str, object],
    runtime_spool_path: str | None,
    runtime_shard_id: str,
    artifact_ingest_base_url: str,
    max_active_sessions: int,
    max_concurrent_turns: int,
    max_queue_depth: int,
    max_spool_bytes: int,
    max_artifact_bytes: int,
    artifact_upload_timeout_seconds: float,
    artifact_recovery_interval_seconds: float,
    deployment_identity=None,
) -> FastAPI:
    if not isinstance(runtime_shard_id, str) or not runtime_shard_id.strip():
        raise ValueError("protocol-v2 requires runtime_shard_id")
    if len(runtime_shard_id) > 200 or runtime_shard_id != runtime_shard_id.strip():
        raise ValueError("runtime_shard_id must be canonical and at most 200 chars")
    if type(max_active_sessions) is not int or max_active_sessions <= 0:
        raise ValueError("max_active_sessions must be positive")
    if artifact_recovery_interval_seconds <= 0:
        raise ValueError("artifact recovery interval must be positive")
    store = RuntimeStore(
        runtime_store_path,
        artifact_spool_path=runtime_spool_path,
        max_spool_bytes=max_spool_bytes,
        max_artifact_bytes=max_artifact_bytes,
    )
    validator = ServiceTokenValidator(service_auth)
    work_admission = _RuntimeWorkAdmission(
        max_concurrent=max_concurrent_turns,
        max_queue_depth=max_queue_depth,
    )
    uploader = (
        ArtifactUploader(
            store=store,
            ingest_base_url=artifact_ingest_base_url,
            timeout_seconds=artifact_upload_timeout_seconds,
        )
        if artifact_ingest_base_url
        else None
    )

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        await store.initialize()
        await store.artifact_spool.probe_writable()
        stop = asyncio.Event()
        recovery_task = None
        if uploader is not None:
            recovery_task = asyncio.create_task(
                uploader.recovery_loop(
                    stop, interval_seconds=artifact_recovery_interval_seconds
                ),
                name=f"runtime-artifact-recovery:{runtime_shard_id}",
            )
        try:
            yield
        finally:
            stop.set()
            if recovery_task is not None:
                try:
                    await asyncio.wait_for(recovery_task, timeout=5)
                except TimeoutError:
                    recovery_task.cancel()
                    try:
                        await recovery_task
                    except asyncio.CancelledError:
                        pass

    app = FastAPI(
        title="Simverse Lab reference runtime", version="2.0", lifespan=_lifespan
    )
    app.state.runtime_store = store
    app.state.service_token_validator = validator
    app.state.runtime_shard_id = runtime_shard_id
    app.state.artifact_uploader = uploader
    app.state.runtime_work_admission = work_admission
    session_locks: dict[str, asyncio.Lock] = {}

    def _session_lock(session_id: str) -> asyncio.Lock:
        return session_locks.setdefault(session_id, asyncio.Lock())

    def _reject_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def _reject_nonfinite_json(value: str):
        raise ValueError(f"non-finite JSON number: {value}")

    def _enforce_json_depth(value: Any) -> None:
        stack = [(value, 1)]
        while stack:
            item, depth = stack.pop()
            if depth > _MAX_RUNTIME_JSON_DEPTH:
                raise ValueError("request JSON exceeds depth cap")
            if isinstance(item, dict):
                stack.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                stack.extend((child, depth + 1) for child in item)

    async def _strict_json_body(request: Request, model_type):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="invalid_content_length"
                ) from exc
            if declared_length < 0:
                raise HTTPException(status_code=400, detail="invalid_content_length")
            if declared_length > MAX_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail="request_body_too_large")

        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail="request_body_too_large")
        try:
            value = json.loads(
                bytes(raw),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite_json,
            )
            _enforce_json_depth(value)
            if model_type in {
                RuntimeArtifactUploadCommand,
                RuntimeArtifactUploadAck,
            }:
                # Protocol fields use StrictInt/StrictBool where coercion is
                # forbidden. Global strict mode would also reject the ISO-8601
                # datetime representation required on the JSON wire.
                body = model_type.model_validate_json(bytes(raw))
            else:
                body = model_type.model_validate(
                    value, strict=model_type is not ControlCommand
                )
            canonical_json_bytes(body, max_bytes=MAX_REQUEST_BYTES)
            return body
        except RequestSchemaError as exc:
            raise HTTPException(status_code=413, detail="request_body_too_large") from exc
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValidationError,
            ValueError,
            RecursionError,
        ) as exc:
            raise HTTPException(status_code=422, detail="invalid_request_body") from exc

    def _authenticate(
        authorization: str | None,
        *,
        action: str,
        expected_binding: ServiceBinding | None = None,
    ) -> ServiceClaims:
        try:
            token = extract_bearer_token(authorization)
            return validator.validate(
                token,
                required_action=action,
                expected_binding=expected_binding,
            )
        except ServiceAuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc

    def _authenticate_path(
        authorization: str | None, *, action: str, sid: str
    ) -> ServiceClaims:
        claims = _authenticate(authorization, action=action)
        if claims.session_id != sid:
            raise HTTPException(status_code=403, detail="binding_mismatch")
        return claims

    def _enforce_binding(
        claims: ServiceClaims, *, run_id: str, session_id: str, epoch: int
    ) -> None:
        if (
            claims.run_id != run_id
            or claims.session_id != session_id
            or claims.epoch != epoch
        ):
            raise HTTPException(status_code=403, detail="binding_mismatch")

    async def _session_for_claims(sid: str, claims: ServiceClaims) -> StoredSession:
        session = await store.get_session(sid)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session.run_id != claims.run_id or session.epoch != claims.epoch:
            raise HTTPException(status_code=403, detail="binding_mismatch")
        return session

    async def _bound_body_session(
        claims: ServiceClaims,
        *,
        sid: str,
        run_id: str,
        body_session_id: str,
        epoch: int,
    ) -> tuple[ServiceClaims, StoredSession]:
        _enforce_binding(
            claims, run_id=run_id, session_id=body_session_id, epoch=epoch
        )
        if sid != body_session_id:
            raise HTTPException(status_code=403, detail="binding_mismatch")
        return claims, await _session_for_claims(sid, claims)

    def _binding(
        body,
        claims: ServiceClaims,
        *,
        action: str,
    ) -> CommandBinding:
        return CommandBinding(
            audience=validator.config.audience,
            command_id=body.command_id,
            jti=claims.jti,
            request_digest=canonical_request_digest(body),
            run_id=body.run_id,
            session_id=getattr(body, "session_id", getattr(body, "client_run_id", "")),
            epoch=body.epoch,
            action=action,
        )

    async def _inspect_command(binding: CommandBinding):
        try:
            return await store.inspect_command(binding)
        except CrossBindingReplay as exc:
            raise HTTPException(
                status_code=403, detail="command_binding_mismatch"
            ) from exc

    async def _claim_command(binding: CommandBinding):
        try:
            return await store.claim_command(binding)
        except CrossBindingReplay as exc:
            raise HTTPException(
                status_code=403, detail="command_binding_mismatch"
            ) from exc

    async def _complete_result_receipt(
        *,
        binding: CommandBinding,
        claim,
        body: ToolResultCommand,
        session: StoredSession,
        loop: dict[str, Any],
    ) -> dict[str, Any]:
        candidate = {
            "receipt_id": claim.receipt.receipt_id,
            "request_digest": binding.request_digest,
            "session_id": session.session_id,
            "turn_id": body.turn_id,
            "intent_id": body.intent_id,
            "action_id": body.action_id,
            "state": "runtime_acked",
            "runtime_state": loop["phase"],
            "cursor": session.next_event_cursor - 1,
        }
        stored = loop.get("last_result_response")
        static_keys = (
            "receipt_id",
            "request_digest",
            "session_id",
            "turn_id",
            "intent_id",
            "action_id",
            "state",
        )
        if not (
            isinstance(stored, dict)
            and all(stored.get(key) == candidate[key] for key in static_keys)
            and stored.get("runtime_state") == loop["phase"]
            and type(stored.get("cursor")) is int
            and stored["cursor"] >= 0
        ):
            stored = candidate
            loop["last_result_response"] = stored
            await store.transition_session(
                session.session_id,
                expected_states=session.state,
                new_state=session.state,
                checkpoint=loop,
            )
        completed = await store.complete_command(binding, response=stored)
        return completed.response

    @staticmethod
    def _stable_uuid(*parts: object) -> str:
        value = ":".join(str(part) for part in parts)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"simverse:runtime-v2:{value}"))

    @staticmethod
    def _turn_id(session_id: str, goal_command_id: str, sequence: int) -> str:
        binding = f"{session_id}:{goal_command_id}:{sequence}"
        return f"turn-{uuid.uuid5(uuid.NAMESPACE_URL, binding).hex}"

    @staticmethod
    def _loop_checkpoint(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("loop_version") != _RUNTIME_LOOP_VERSION:
            raise RuntimeStoreConflict("runtime loop checkpoint is missing or invalid")
        if value.get("phase") not in {
            "awaiting_model",
            "awaiting_result_model",
            "persisting_turn",
            "intent_pending",
            "completed",
            "failed",
        }:
            raise RuntimeStoreConflict("runtime loop checkpoint phase is invalid")
        if type(value.get("turn_sequence")) is not int or value["turn_sequence"] < 0:
            raise RuntimeStoreConflict("runtime loop turn sequence is invalid")
        if not isinstance(value.get("agent_checkpoint"), dict):
            raise RuntimeStoreConflict("runtime loop agent checkpoint is invalid")
        return value

    def _artifact_content(turn_artifact) -> tuple[bytes, str, str | None, int, str]:
        if turn_artifact.uri is not None:
            raise RuntimeStoreConflict(
                "runtime artifacts cannot read arbitrary URI or host paths"
            )
        binary_bytes = getattr(turn_artifact, "content_bytes", None)
        binary_base64 = getattr(turn_artifact, "content_base64", None)
        if binary_bytes is not None and binary_base64 is not None:
            raise RuntimeStoreConflict("runtime artifact has multiple byte sources")
        if binary_bytes is not None or binary_base64 is not None:
            if turn_artifact.text_md is not None:
                raise RuntimeStoreConflict("runtime artifact has multiple byte sources")
            if binary_bytes is not None:
                if not isinstance(binary_bytes, bytes):
                    raise RuntimeStoreConflict("runtime artifact bytes are invalid")
                content = binary_bytes
            else:
                if not isinstance(binary_base64, str):
                    raise RuntimeStoreConflict("runtime artifact base64 is invalid")
                encoded_cap = (
                    (store.artifact_spool.max_artifact_bytes + 2) // 3
                ) * 4
                if len(binary_base64) > encoded_cap:
                    raise RuntimeStoreBackpressure(
                        "runtime artifact exceeds byte cap"
                    )
                try:
                    content = base64.b64decode(binary_base64, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise RuntimeStoreConflict(
                        "runtime artifact base64 is invalid"
                    ) from exc
                if base64.b64encode(content).decode("ascii") != binary_base64:
                    raise RuntimeStoreConflict(
                        "runtime artifact base64 is not canonical"
                    )
            content_type = getattr(turn_artifact, "content_type", None)
            original_filename = getattr(turn_artifact, "original_filename", None)
            declared_byte_size = getattr(
                turn_artifact, "declared_byte_size", None
            )
            expected_sha256 = getattr(turn_artifact, "expected_sha256", None)
            if (
                not isinstance(content_type, str)
                or not content_type
                or not isinstance(original_filename, str)
                or not original_filename
                or type(declared_byte_size) is not int
                or not isinstance(expected_sha256, str)
            ):
                raise RuntimeStoreConflict(
                    "binary runtime artifact declaration is incomplete"
                )
        else:
            if not isinstance(turn_artifact.text_md, str):
                raise RuntimeStoreConflict("runtime artifact has no byte source")
            redacted_text = guard.redact_text(turn_artifact.text_md) or ""
            content = redacted_text.encode("utf-8")
            content_type = (
                getattr(turn_artifact, "content_type", None)
                or (
                    "text/markdown; charset=utf-8"
                    if turn_artifact.kind == "text"
                    else "text/plain; charset=utf-8"
                )
            )
            original_filename = getattr(
                turn_artifact, "original_filename", None
            ) or (
                "research-summary.md" if turn_artifact.kind == "text" else None
            )
            declared_byte_size = getattr(
                turn_artifact, "declared_byte_size", None
            )
            if declared_byte_size is None:
                declared_byte_size = len(content)
            expected_sha256 = getattr(turn_artifact, "expected_sha256", None)
            if expected_sha256 is None:
                expected_sha256 = hashlib.sha256(content).hexdigest()

        actual_sha256 = hashlib.sha256(content).hexdigest()
        if declared_byte_size != len(content) or expected_sha256 != actual_sha256:
            raise RuntimeStoreConflict("runtime artifact byte declaration mismatch")
        return (
            content,
            content_type,
            original_filename,
            declared_byte_size,
            expected_sha256,
        )

    async def _serialized_turn(
        turn: AgentTurn, *, turn_id: str, session_id: str
    ) -> dict[str, Any]:
        artifact = None
        if turn.artifact is not None:
            if turn.state != "final":
                raise RuntimeStoreConflict(
                    "runtime artifact is only valid on a final turn"
                )
            artifact_id = _stable_uuid(session_id, "artifact", turn_id)
            (
                content,
                content_type,
                original_filename,
                declared_byte_size,
                expected_sha256,
            ) = _artifact_content(turn.artifact)
            title = guard.redact_text(turn.artifact.title) or ""
            meta = guard.redact_payload(turn.artifact.meta)
            required = getattr(turn.artifact, "required", True)
            store.artifact_declaration(
                artifact_id=artifact_id,
                kind=turn.artifact.kind,
                title=title,
                content_type=content_type,
                original_filename=original_filename,
                declared_byte_size=declared_byte_size,
                expected_sha256=expected_sha256,
                required=required,
                producer_action_id=None,
                meta=meta,
            )
            spooled = await store.stage_artifact_bytes(
                session_id,
                artifact_id,
                content=content,
                declared_byte_size=declared_byte_size,
                expected_sha256=expected_sha256,
            )
            artifact = {
                "artifact_id": artifact_id,
                "kind": turn.artifact.kind,
                "title": title,
                "meta": meta,
                "content_type": content_type,
                "original_filename": original_filename,
                "declared_byte_size": declared_byte_size,
                "expected_sha256": expected_sha256,
                "required": required,
                "spool_locator": spooled.locator,
            }
        tool_intent = None
        if turn.tool_intent is not None:
            tool_intent = [turn.tool_intent[0], turn.tool_intent[1]]
        return {
            "state": turn.state,
            "turn_id": turn_id,
            "agent_checkpoint": turn.checkpoint,
            "steps": [
                {
                    "phase": step.phase,
                    "tool": step.tool,
                    "summary": guard.redact_text(step.summary) or "",
                    "payload": step.payload,
                    "model_tokens": step.model_tokens,
                }
                for step in turn.steps
            ],
            "tool_intent": tool_intent,
            "artifact": artifact,
        }

    async def _append_event(
        session: StoredSession,
        *,
        event_kind: str,
        payload: dict,
        dedupe_key: str,
        turn_id: str | None = None,
        intent_id: str | None = None,
        outcome: str | None = None,
        tool_name: str | None = None,
        tool_args: dict | None = None,
    ):
        current = await store.get_session(session.session_id)
        if current is None:
            raise RuntimeStoreNotFound("session not found")
        if current.run_id != session.run_id or current.epoch != session.epoch:
            raise RuntimeStoreConflict("session event binding changed")
        event_id = _stable_uuid(session.session_id, dedupe_key)
        tool_digest = args_digest(tool_args) if tool_args is not None else None
        candidate = RuntimeEvent(
            event_id=event_id,
            run_id=session.run_id,
            session_id=session.session_id,
            cursor=current.next_event_cursor,
            epoch=session.epoch,
            event_kind=event_kind,
            turn_id=turn_id,
            intent_id=intent_id,
            outcome=outcome,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_args_digest=tool_digest,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
        encoded_size = len(canonical_json_bytes(
            candidate.model_dump(mode="json"), max_bytes=MAX_EVENT_BYTES
        ))
        return await store.append_event(
            session.session_id,
            event_kind=candidate.event_kind,
            turn_id=candidate.turn_id,
            intent_id=candidate.intent_id,
            outcome=candidate.outcome,
            tool_name=candidate.tool_name,
            tool_args=candidate.tool_args,
            tool_args_digest=candidate.tool_args_digest,
            payload=candidate.payload,
            encoded_size=encoded_size,
            event_id=candidate.event_id,
            dedupe_key=dedupe_key,
        )

    async def _persist_turn(
        session: StoredSession,
        loop: dict[str, Any],
        *,
        expected_state: str,
    ) -> tuple[StoredSession, dict[str, Any]]:
        pending = loop.get("pending_turn")
        if not isinstance(pending, dict):
            raise RuntimeStoreConflict("runtime turn output was not checkpointed")
        turn_id = pending.get("turn_id")
        if not isinstance(turn_id, str) or not turn_id:
            raise RuntimeStoreConflict("runtime turn id is invalid")
        steps = pending.get("steps")
        if not isinstance(steps, list) or not steps:
            raise RuntimeStoreConflict("runtime turn has no model steps")
        think = steps[0]
        await _append_event(
            session,
            event_kind="think",
            turn_id=turn_id,
            payload={
                "summary": think.get("summary", ""),
                "model_tokens": think.get("model_tokens", 0),
            },
            dedupe_key=f"turn:{turn_id}:think",
        )

        state = pending.get("state")
        loop["agent_checkpoint"] = pending["agent_checkpoint"]
        loop["last_turn_id"] = turn_id
        loop["turn_sequence"] += 1
        provenance = loop.get("broker_results") or []
        latest_result = provenance[-1] if provenance else None
        broker_terminal_failure = (
            isinstance(latest_result, dict)
            and latest_result.get("outcome") in {"denied", "failed"}
        )
        if state == "intent":
            if broker_terminal_failure:
                reason = steps[-1].get(
                    "summary", f"broker result {latest_result['outcome']}"
                )
                await _append_event(
                    session,
                    event_kind="failed",
                    turn_id=turn_id,
                    payload={"summary": reason},
                    dedupe_key=f"turn:{turn_id}:failed",
                )
                loop.update({
                    "phase": "failed",
                    "active_intent_id": None,
                    "pending_turn": None,
                })
                updated = await store.transition_session(
                    session.session_id,
                    expected_states=expected_state,
                    new_state="failed",
                    checkpoint=loop,
                )
                return updated, loop
            raw_intent = pending.get("tool_intent")
            if (
                not isinstance(raw_intent, list)
                or len(raw_intent) != 2
                or not isinstance(raw_intent[0], str)
                or not isinstance(raw_intent[1], dict)
            ):
                raise RuntimeStoreConflict("runtime tool intent is invalid")
            tool, args = raw_intent
            intent_id = f"intent-{_stable_uuid(session.session_id, turn_id, tool)}"
            await store.record_intent(
                session.session_id,
                turn_id=turn_id,
                intent_id=intent_id,
                tool=tool,
                args=args,
            )
            summary = steps[-1].get("summary", "")
            await _append_event(
                session,
                event_kind="tool_intent",
                turn_id=turn_id,
                intent_id=intent_id,
                tool_name=tool,
                tool_args=args,
                payload={"summary": summary},
                dedupe_key=f"intent:{intent_id}",
            )
            loop.update({
                "phase": "intent_pending",
                "active_intent_id": intent_id,
                "pending_turn": None,
            })
            updated = await store.transition_session(
                session.session_id,
                expected_states=expected_state,
                new_state="intent_pending",
                checkpoint=loop,
            )
            return updated, loop

        if state == "final":
            artifact = pending.get("artifact")
            if not isinstance(artifact, dict):
                raise RuntimeStoreConflict("final turn has no artifact")
            summary = steps[-1].get("summary", "")
            await _append_event(
                session,
                event_kind="final",
                turn_id=turn_id,
                payload={"summary": summary},
                dedupe_key=f"turn:{turn_id}:final",
            )
            if broker_terminal_failure:
                spool_locator = artifact.get("spool_locator")
                if isinstance(spool_locator, str):
                    try:
                        await store.artifact_spool.delete(spool_locator)
                    except (ArtifactSpoolError, OSError, ValueError):
                        pass
                loop.update({
                    "phase": "failed",
                    "active_intent_id": None,
                    "pending_turn": None,
                })
                updated = await store.transition_session(
                    session.session_id,
                    expected_states=expected_state,
                    new_state="failed",
                    checkpoint=loop,
                )
                return updated, loop
            artifact_id = _stable_uuid(session.session_id, "artifact", turn_id)
            if artifact.get("artifact_id") != artifact_id:
                raise RuntimeStoreConflict("runtime artifact binding changed")
            meta = dict(artifact.get("meta") or {})
            producer_action_id = None
            if provenance:
                latest = provenance[-1]
                producer_action_id = latest["action_id"]
                meta.update({
                    "broker_result_digest": latest["result_digest"],
                    "broker_result_provenance": {
                        "command_id": latest["command_id"],
                        "intent_id": latest["intent_id"],
                        "action_id": latest["action_id"],
                    },
                    "broker_results": provenance,
                })
            await store.put_artifact_from_spool(
                session.session_id,
                artifact_id=artifact_id,
                kind=artifact["kind"],
                title=artifact["title"],
                spool_locator=artifact["spool_locator"],
                meta=meta,
                content_type=artifact["content_type"],
                original_filename=artifact.get("original_filename"),
                declared_byte_size=artifact["declared_byte_size"],
                expected_sha256=artifact["expected_sha256"],
                required=artifact["required"],
                producer_action_id=producer_action_id,
            )
            loop.update({
                "phase": "completed",
                "active_intent_id": None,
                "pending_turn": None,
            })
            updated = await store.transition_session(
                session.session_id,
                expected_states=expected_state,
                new_state="completed",
                checkpoint=loop,
            )
            return updated, loop

        if state != "failed":
            raise RuntimeStoreConflict("runtime turn terminal state is invalid")
        reason = steps[-1].get("summary", "runtime model turn failed")
        await _append_event(
            session,
            event_kind="failed",
            turn_id=turn_id,
            payload={"summary": reason},
            dedupe_key=f"turn:{turn_id}:failed",
        )
        loop.update({
            "phase": "failed",
            "active_intent_id": None,
            "pending_turn": None,
        })
        updated = await store.transition_session(
            session.session_id,
            expected_states=expected_state,
            new_state="failed",
            checkpoint=loop,
        )
        return updated, loop

    @app.get("/handshake")
    async def handshake_v2(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        _authenticate(authorization, action="runtime.handshake")
        capabilities = {
            "backpressure",
            "broker_mediation",
            "cancel",
            "control",
            "cursor_replay",
            "events_ack",
            "idempotent_create",
            "kill",
            "reattach",
            "result_receipts",
            "scoped_auth",
            "terminate",
        }
        manifest = RuntimeV2Handshake(
            protocol_version=2,
            provider_name="simverse_ref",
            durability_class="session_affine",
            reattach_capability="client_run_id",
            effect_mode="broker_only",
            capabilities=sorted(capabilities),
        )
        return runtime_v2_supervision_handshake(manifest).model_dump(mode="json")

    @app.get("/livez")
    async def livez():
        payload = {
            "alive": True,
            "service": "lab-runtime",
            "protocol_version": 2,
            "runtime_shard_id": runtime_shard_id,
        }
        if deployment_identity is not None:
            payload.update(deployment_identity.health_fields())
        return payload

    @app.get("/readyz")
    async def readyz():
        if uploader is None:
            return JSONResponse(
                status_code=503,
                content={
                    "ready": False,
                    "service": "lab-runtime",
                    "reason": "artifact_ingest_not_configured",
                    "runtime_shard_id": runtime_shard_id,
                },
            )
        try:
            store_status = await store.readiness()
            await store.artifact_spool.probe_writable()
            work_status = await work_admission.status()
        except Exception:
            return JSONResponse(
                status_code=503,
                content={
                    "ready": False,
                    "service": "lab-runtime",
                    "reason": "durable_storage_unavailable",
                    "runtime_shard_id": runtime_shard_id,
                },
            )
        if store_status["active_sessions"] >= max_active_sessions:
            reason = "session_capacity_reached"
        elif store_status["spool_bytes"] >= store.artifact_spool.max_bytes:
            reason = "artifact_spool_capacity_reached"
        elif work_status["queue_depth"] >= max_queue_depth and max_queue_depth > 0:
            reason = "runtime_queue_capacity_reached"
        else:
            reason = None
        content = {
            "ready": reason is None,
            "service": "lab-runtime",
            "protocol_version": 2,
            "runtime_shard_id": runtime_shard_id,
            "active_sessions": store_status["active_sessions"],
            "spool_bytes": store_status["spool_bytes"],
            "running_turns": work_status["running_turns"],
            "queue_depth": work_status["queue_depth"],
        }
        if reason is not None:
            content["reason"] = reason
            return JSONResponse(status_code=503, content=content)
        return content

    @app.post("/runs", status_code=201)
    async def start_run_v2(
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate(authorization, action="session.create")
        body = await _strict_json_body(request, V2StartBody)
        _enforce_binding(
            claims,
            run_id=body.run_id,
            session_id=body.client_run_id,
            epoch=body.epoch,
        )
        request_digest = canonical_request_digest(body)
        binding = CommandBinding(
            audience=validator.config.audience,
            command_id=body.command_id,
            jti=claims.jti,
            request_digest=request_digest,
            run_id=body.run_id,
            session_id=body.client_run_id,
            epoch=body.epoch,
            action="session.create",
        )
        try:
            claim = await store.claim_command(binding)
            if claim.is_retry and claim.receipt.state == "completed":
                return claim.receipt.response
            session = await store.create_or_get_session(
                run_id=body.run_id,
                client_run_id=body.client_run_id,
                epoch=body.epoch,
                scopes=body.scopes,
                budget_usd=body.budget_usd,
                egress_allowlist=body.egress_allowlist,
                max_active_sessions=max_active_sessions,
            )
            started = await _append_event(
                session,
                event_kind="session_started",
                payload={},
                dedupe_key="session:started",
            )
            response = {
                "session_id": session.session_id,
                "receipt_id": claim.receipt.receipt_id,
                "request_digest": request_digest,
                "cursor": started.cursor,
            }
            completed = await store.complete_command(binding, response=response)
            return completed.response
        except CrossBindingReplay as exc:
            raise HTTPException(status_code=403, detail="command_binding_mismatch") from exc
        except RuntimeStoreBackpressure as exc:
            raise HTTPException(status_code=429, detail="runtime_capacity_reached") from exc
        except RuntimeStoreConflict as exc:
            raise HTTPException(status_code=409, detail="session_binding_conflict") from exc

    @app.post("/runs/{sid}/goal")
    async def submit_goal_v2(
        sid: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="goal.submit", sid=sid
        )
        body = await _strict_json_body(request, V2GoalBody)
        _enforce_binding(
            claims,
            run_id=body.run_id,
            session_id=body.session_id,
            epoch=body.epoch,
        )
        if sid != body.session_id:
            raise HTTPException(status_code=403, detail="binding_mismatch")
        binding = _binding(body, claims, action="goal.submit")
        known = await _inspect_command(binding)
        if known is not None and known.state == "completed":
            return known.response
        session = await _session_for_claims(sid, claims)
        requested_scopes = tuple(sorted(set(body.scopes or session.scopes)))
        if not set(requested_scopes) <= set(session.scopes):
            raise HTTPException(status_code=403, detail="scope_escalation")
        claim = await _claim_command(binding)
        if claim.is_retry and claim.receipt.state == "completed":
            return claim.receipt.response

        async with _session_lock(sid):
            known = await _inspect_command(binding)
            if known is not None and known.state == "completed":
                return known.response
            session = await _session_for_claims(sid, claims)
            try:
                if session.state == "created":
                    loop = {
                        "loop_version": _RUNTIME_LOOP_VERSION,
                        "goal_command_id": body.command_id,
                        "goal_request_digest": binding.request_digest,
                        "agent_checkpoint": RefAgent.initial_checkpoint(
                            brief=body.brief,
                            scopes=list(requested_scopes),
                        ),
                        "phase": "awaiting_model",
                        "turn_sequence": 0,
                        "active_intent_id": None,
                        "pending_turn": None,
                        "broker_results": [],
                    }
                    try:
                        canonical_json_bytes(loop, max_bytes=MAX_UNACKED_BYTES)
                    except RequestSchemaError as exc:
                        raise HTTPException(
                            status_code=413,
                            detail="runtime_checkpoint_too_large",
                        ) from exc
                    session = await store.transition_session(
                        sid,
                        expected_states="created",
                        new_state="running",
                        checkpoint=loop,
                    )
                else:
                    loop = _loop_checkpoint(session.checkpoint)
                    if (
                        loop.get("goal_command_id") != body.command_id
                        or loop.get("goal_request_digest") != binding.request_digest
                    ):
                        raise RuntimeStoreConflict(
                            "session is already bound to another goal"
                        )

                if loop["phase"] == "awaiting_model":
                    agent = RefAgent(
                        complete=completer_factory(), max_steps=max_steps
                    )
                    async with work_admission.slot():
                        turn = await agent.advance_turn(loop["agent_checkpoint"])
                    turn_id = _turn_id(
                        sid, body.command_id, loop["turn_sequence"]
                    )
                    loop["pending_turn"] = await _serialized_turn(
                        turn, turn_id=turn_id, session_id=sid
                    )
                    loop["phase"] = "persisting_turn"
                    session = await store.transition_session(
                        sid,
                        expected_states="running",
                        new_state="running",
                        checkpoint=loop,
                    )

                if loop["phase"] == "persisting_turn":
                    session, loop = await _persist_turn(
                        session, loop, expected_state="running"
                    )
                if loop["phase"] not in {"intent_pending", "completed", "failed"}:
                    raise RuntimeStoreConflict("goal did not reach a durable pause")

                response = {
                    "receipt_id": claim.receipt.receipt_id,
                    "request_digest": binding.request_digest,
                    "session_id": sid,
                    "turn_id": loop["last_turn_id"],
                    "state": loop["phase"],
                    "cursor": session.next_event_cursor - 1,
                }
                completed = await store.complete_command(
                    binding, response=response
                )
                return completed.response
            except _RuntimeWorkBackpressure as exc:
                raise HTTPException(status_code=429, detail="runtime_queue_full") from exc
            except RuntimeStoreBackpressure as exc:
                raise HTTPException(status_code=429, detail="event_backpressure") from exc
            except RequestSchemaError as exc:
                raise HTTPException(
                    status_code=413, detail="runtime_checkpoint_too_large"
                ) from exc
            except (RuntimeStoreConflict, RuntimeStoreNotFound, ValueError) as exc:
                raise HTTPException(status_code=409, detail="runtime_goal_conflict") from exc

    @app.post("/runs/{sid}/results")
    async def submit_result_v2(
        sid: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="tool_result.submit", sid=sid
        )
        body = await _strict_json_body(request, ToolResultCommand)
        _enforce_binding(
            claims,
            run_id=body.run_id,
            session_id=body.session_id,
            epoch=body.epoch,
        )
        if sid != body.session_id:
            raise HTTPException(status_code=403, detail="binding_mismatch")
        redacted_payload = guard.redact_payload(body.payload)
        try:
            canonical_json_bytes(
                body.payload, max_bytes=MAX_COMMAND_BYTES
            )
            canonical_json_bytes(
                redacted_payload, max_bytes=MAX_COMMAND_BYTES
            )
        except RequestSchemaError as exc:
            raise HTTPException(
                status_code=413, detail="model_result_payload_too_large"
            ) from exc

        binding = _binding(body, claims, action="tool_result.submit")
        known = await _inspect_command(binding)
        if known is not None and known.state == "completed":
            return known.response
        session = await _session_for_claims(sid, claims)
        claim = await _claim_command(binding)
        if claim.is_retry and claim.receipt.state == "completed":
            return claim.receipt.response

        async with _session_lock(sid):
            known = await _inspect_command(binding)
            if known is not None and known.state == "completed":
                return known.response
            session = await _session_for_claims(sid, claims)
            try:
                loop = _loop_checkpoint(session.checkpoint)
                intent = await store.get_intent(sid, body.intent_id)
                if intent is None:
                    raise RuntimeStoreNotFound("result intent does not exist")
                if intent.turn_id != body.turn_id:
                    raise RuntimeStoreConflict("result turn binding mismatch")

                if (
                    loop.get("last_result_command_id") == body.command_id
                    and intent.state == "applied"
                    and loop["phase"] in {"intent_pending", "completed", "failed"}
                    and session.state == loop["phase"]
                ):
                    await store.resolve_intent(
                        sid,
                        intent_id=body.intent_id,
                        turn_id=body.turn_id,
                        command_id=body.command_id,
                        action_id=body.action_id,
                        result_digest=body.result_digest,
                        outcome=body.outcome,
                        payload=body.payload,
                        stored_payload=redacted_payload,
                    )
                    return await _complete_result_receipt(
                        binding=binding,
                        claim=claim,
                        body=body,
                        session=session,
                        loop=loop,
                    )

                if session.state == "intent_pending":
                    if (
                        loop["phase"] != "intent_pending"
                        or loop.get("active_intent_id") != body.intent_id
                    ):
                        raise RuntimeStoreConflict("result is not for the active intent")
                    intent = await store.resolve_intent(
                        sid,
                        intent_id=body.intent_id,
                        turn_id=body.turn_id,
                        command_id=body.command_id,
                        action_id=body.action_id,
                        result_digest=body.result_digest,
                        outcome=body.outcome,
                        payload=body.payload,
                        stored_payload=redacted_payload,
                    )
                    result_event = await _append_event(
                        session,
                        event_kind="tool_result",
                        turn_id=body.turn_id,
                        intent_id=body.intent_id,
                        outcome=body.outcome,
                        payload=redacted_payload,
                        dedupe_key=f"result:{body.intent_id}",
                    )
                    provenance = {
                        "command_id": body.command_id,
                        "intent_id": body.intent_id,
                        "action_id": body.action_id,
                        "outcome": body.outcome,
                        "result_digest": body.result_digest,
                    }
                    existing_results = loop.setdefault("broker_results", [])
                    if provenance not in existing_results:
                        existing_results.append(provenance)
                    loop.update({
                        "phase": "awaiting_result_model",
                        "resume_result": {
                            "command_id": body.command_id,
                            "intent_id": body.intent_id,
                            "turn_id": body.turn_id,
                            "tool": intent.tool,
                            "outcome": intent.result_outcome,
                            "payload": intent.result_payload,
                            "result_event_cursor": result_event.cursor,
                        },
                        "last_result_command_id": body.command_id,
                    })
                    session = await store.transition_session(
                        sid,
                        expected_states="intent_pending",
                        new_state="resuming",
                        checkpoint=loop,
                    )
                elif session.state == "resuming":
                    if (
                        loop.get("last_result_command_id") != body.command_id
                        or loop.get("resume_result", {}).get("intent_id")
                        != body.intent_id
                    ):
                        raise RuntimeStoreConflict(
                            "session is resuming another result command"
                        )
                    await store.resolve_intent(
                        sid,
                        intent_id=body.intent_id,
                        turn_id=body.turn_id,
                        command_id=body.command_id,
                        action_id=body.action_id,
                        result_digest=body.result_digest,
                        outcome=body.outcome,
                        payload=body.payload,
                        stored_payload=redacted_payload,
                    )
                elif loop.get("last_result_command_id") != body.command_id:
                    raise RuntimeStoreConflict("session no longer accepts this result")

                if loop["phase"] == "awaiting_result_model":
                    resume = loop["resume_result"]
                    agent = RefAgent(
                        complete=completer_factory(), max_steps=max_steps
                    )
                    async with work_admission.slot():
                        turn = await agent.resume_turn(
                            checkpoint=loop["agent_checkpoint"],
                            tool=resume["tool"],
                            outcome=resume["outcome"],
                            payload=resume["payload"],
                        )
                    turn_id = _turn_id(
                        sid,
                        loop["goal_command_id"],
                        loop["turn_sequence"],
                    )
                    loop["pending_turn"] = await _serialized_turn(
                        turn, turn_id=turn_id, session_id=sid
                    )
                    loop["phase"] = "persisting_turn"
                    session = await store.transition_session(
                        sid,
                        expected_states="resuming",
                        new_state="resuming",
                        checkpoint=loop,
                    )

                if loop["phase"] == "persisting_turn":
                    await store.mark_intent_applied(sid, body.intent_id)
                    session, loop = await _persist_turn(
                        session, loop, expected_state="resuming"
                    )
                if loop["phase"] not in {"intent_pending", "completed", "failed"}:
                    raise RuntimeStoreConflict("result did not reach a durable pause")

                return await _complete_result_receipt(
                    binding=binding,
                    claim=claim,
                    body=body,
                    session=session,
                    loop=loop,
                )
            except _RuntimeWorkBackpressure as exc:
                raise HTTPException(status_code=429, detail="runtime_queue_full") from exc
            except RuntimeStoreBackpressure as exc:
                raise HTTPException(status_code=429, detail="event_backpressure") from exc
            except RequestSchemaError as exc:
                raise HTTPException(
                    status_code=413, detail="runtime_checkpoint_too_large"
                ) from exc
            except (RuntimeStoreConflict, RuntimeStoreNotFound, ValueError) as exc:
                raise HTTPException(status_code=409, detail="runtime_result_conflict") from exc

    @app.get("/runs/{sid}/events")
    async def events_v2(
        sid: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="events.read", sid=sid
        )
        def _bounded_query_int(
            name: str, *, default: int, minimum: int, maximum: int
        ) -> int:
            values = request.query_params.getlist(name)
            if not values:
                return default
            if len(values) != 1 or not values[0].isdecimal():
                raise HTTPException(
                    status_code=422, detail=f"invalid event {name}"
                )
            value = int(values[0])
            if not minimum <= value <= maximum:
                raise HTTPException(
                    status_code=422, detail=f"invalid event {name}"
                )
            return value

        after = _bounded_query_int(
            "after", default=0, minimum=0, maximum=2**63 - 1
        )
        limit = _bounded_query_int(
            "limit",
            default=MAX_UNACKED_EVENTS,
            minimum=1,
            maximum=MAX_UNACKED_EVENTS,
        )
        max_bytes = _bounded_query_int(
            "max_bytes",
            default=MAX_UNACKED_BYTES,
            minimum=1,
            maximum=MAX_UNACKED_BYTES,
        )
        session = await _session_for_claims(sid, claims)
        latest_cursor = session.next_event_cursor - 1
        if after > latest_cursor:
            raise HTTPException(status_code=422, detail="invalid event cursor")
        try:
            events = await store.list_events(sid, after=after, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid event cursor") from exc
        encoded_events: list[dict[str, Any]] = []
        encoded_bytes = 0
        for event in events:
            envelope = RuntimeEvent(
                event_id=event.event_id,
                run_id=session.run_id,
                session_id=session.session_id,
                cursor=event.cursor,
                epoch=session.epoch,
                event_kind=event.event_kind,
                turn_id=event.turn_id,
                intent_id=event.intent_id,
                outcome=event.outcome,
                tool_name=event.tool_name,
                tool_args=event.tool_args,
                tool_args_digest=event.tool_args_digest,
                payload=event.payload,
                occurred_at=event.occurred_at,
            ).model_dump(mode="json")
            size = len(canonical_json_bytes(envelope, max_bytes=MAX_EVENT_BYTES))
            if encoded_bytes + size > max_bytes:
                break
            encoded_events.append(envelope)
            encoded_bytes += size
        delivered_through = (
            encoded_events[-1]["cursor"] if encoded_events else after
        )
        has_more = delivered_through < latest_cursor
        return {
            "events": encoded_events,
            "done": (
                session.state in {"completed", "failed", "cancelled"}
                and not has_more
            ),
            "has_more": has_more,
            "latest_cursor": latest_cursor,
            "acked_through": session.acked_event_cursor,
        }

    @app.post("/runs/{sid}/events/ack")
    async def acknowledge_events_v2(
        sid: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="events.ack", sid=sid
        )
        body = await _strict_json_body(request, V2EventAckBody)
        _enforce_binding(
            claims,
            run_id=body.run_id,
            session_id=body.session_id,
            epoch=body.epoch,
        )
        if sid != body.session_id:
            raise HTTPException(status_code=403, detail="binding_mismatch")
        binding = _binding(body, claims, action="events.ack")
        known = await _inspect_command(binding)
        if known is not None and known.state == "completed":
            return known.response
        session = await _session_for_claims(sid, claims)
        if (
            body.cursor > session.next_event_cursor - 1
            or body.cursor < session.acked_event_cursor
        ):
            raise HTTPException(status_code=409, detail="event_ack_conflict")
        claim = await _claim_command(binding)
        if claim.is_retry and claim.receipt.state == "completed":
            return claim.receipt.response
        async with _session_lock(sid):
            known = await _inspect_command(binding)
            if known is not None and known.state == "completed":
                return known.response
            try:
                session = await store.acknowledge_events(
                    sid, cursor=body.cursor
                )
                response = {
                    "receipt_id": claim.receipt.receipt_id,
                    "request_digest": binding.request_digest,
                    "session_id": sid,
                    "acked_through": session.acked_event_cursor,
                }
                completed = await store.complete_command(
                    binding, response=response
                )
                return completed.response
            except (RuntimeStoreConflict, RuntimeStoreNotFound, ValueError) as exc:
                raise HTTPException(status_code=409, detail="event_ack_conflict") from exc

    @app.get("/runs/{sid}/steps")
    async def steps_v2(
        sid: str,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="events.read", sid=sid
        )
        await _session_for_claims(sid, claims)
        raise HTTPException(
            status_code=501, detail="protocol-v2 uses the RuntimeEvent stream"
        )

    @app.get("/runs/{sid}/artifacts")
    async def artifacts_v2(
        sid: str,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="artifacts.read", sid=sid
        )
        session = await _session_for_claims(sid, claims)
        if session.state != "completed" or await store.count_active_intents(sid):
            raise HTTPException(status_code=409, detail="artifacts pending")
        artifacts = await store.list_artifacts(sid)
        return {
            "artifacts": [
                RuntimeArtifactManifest(
                    provider_artifact_id=artifact.artifact_id,
                    kind=artifact.kind,
                    title=artifact.title,
                    content_type=artifact.content_type,
                    original_filename=artifact.original_filename,
                    declared_byte_size=artifact.declared_byte_size,
                    expected_sha256=artifact.expected_sha256,
                    required=(
                        False
                        if artifact.upload_state == "legacy_inline"
                        and artifact.kind == "link"
                        else artifact.required
                    ),
                    producer_action_id=artifact.producer_action_id,
                    upload_state=(
                        artifact.upload_state
                        if artifact.upload_state != "legacy_inline"
                        else "failed"
                    ),
                    upload_receipt=artifact.upload_receipt,
                ).model_dump(mode="json")
                for artifact in artifacts
            ]
        }

    @app.post("/runs/{sid}/artifacts/{provider_artifact_id}/upload")
    async def upload_artifact_v2(
        sid: str,
        provider_artifact_id: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        if uploader is None:
            raise HTTPException(
                status_code=503, detail="artifact_upload_not_configured"
            )
        claims = _authenticate_path(
            authorization, action="artifacts.upload", sid=sid
        )
        body = await _strict_json_body(request, RuntimeArtifactUploadCommand)
        await _bound_body_session(
            claims,
            sid=sid,
            run_id=body.run_id,
            body_session_id=body.session_id,
            epoch=body.epoch,
        )
        if body.provider_artifact_id != provider_artifact_id:
            raise HTTPException(status_code=403, detail="binding_mismatch")
        binding = _binding(body, claims, action="artifacts.upload")
        known = await _inspect_command(binding)
        if known is not None and known.state == "completed":
            return known.response
        session = await _session_for_claims(sid, claims)
        if session.state != "completed" or await store.count_active_intents(sid):
            raise HTTPException(status_code=409, detail="artifacts pending")
        claim = await _claim_command(binding)
        if claim.is_retry and claim.receipt.state == "completed":
            return claim.receipt.response
        try:
            artifact = await uploader.execute(
                body, command_digest=binding.request_digest
            )
            if (
                artifact.upload_receipt is None
                or artifact.upload_receipt_digest is None
                or artifact.upload_id is None
            ):
                raise RuntimeStoreConflict("artifact upload has no durable receipt")
            response = {
                "receipt_id": claim.receipt.receipt_id,
                "request_digest": binding.request_digest,
                "runtime_shard_id": runtime_shard_id,
                "session_id": sid,
                "provider_artifact_id": provider_artifact_id,
                "upload_id": artifact.upload_id,
                "state": artifact.upload_state,
                "upload_receipt": artifact.upload_receipt,
                "upload_receipt_digest": artifact.upload_receipt_digest,
            }
            completed = await store.complete_command(binding, response=response)
            return completed.response
        except ArtifactUploadError as exc:
            raise HTTPException(
                status_code=503 if exc.retryable else 409,
                detail=exc.error_code,
            ) from exc
        except (RuntimeStoreConflict, RuntimeStoreNotFound, ValueError) as exc:
            raise HTTPException(status_code=409, detail="artifact_upload_conflict") from exc

    @app.post("/runs/{sid}/artifacts/{provider_artifact_id}/upload/ack")
    async def acknowledge_artifact_upload_v2(
        sid: str,
        provider_artifact_id: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="artifacts.upload.ack", sid=sid
        )
        body = await _strict_json_body(request, RuntimeArtifactUploadAck)
        await _bound_body_session(
            claims,
            sid=sid,
            run_id=body.run_id,
            body_session_id=body.session_id,
            epoch=body.epoch,
        )
        if body.provider_artifact_id != provider_artifact_id:
            raise HTTPException(status_code=403, detail="binding_mismatch")
        binding = _binding(body, claims, action="artifacts.upload.ack")
        known = await _inspect_command(binding)
        if known is not None and known.state == "completed":
            return known.response
        claim = await _claim_command(binding)
        if claim.is_retry and claim.receipt.state == "completed":
            return claim.receipt.response
        try:
            artifact = await store.acknowledge_artifact_upload(
                sid,
                provider_artifact_id,
                receipt_digest=body.upload_receipt_digest,
            )
            spool_deleted = artifact.spool_deleted_at is not None
            if not spool_deleted and artifact.spool_locator is not None:
                try:
                    await store.artifact_spool.delete(artifact.spool_locator)
                    artifact = await store.mark_artifact_spool_deleted(
                        sid, provider_artifact_id
                    )
                    spool_deleted = artifact.spool_deleted_at is not None
                except Exception:
                    # The durable ACK is the authorization boundary. Startup and
                    # the recovery loop finish an interrupted local deletion.
                    spool_deleted = False
            response = {
                "receipt_id": claim.receipt.receipt_id,
                "request_digest": binding.request_digest,
                "runtime_shard_id": runtime_shard_id,
                "session_id": sid,
                "provider_artifact_id": provider_artifact_id,
                "state": "acknowledged",
                "upload_receipt_digest": body.upload_receipt_digest,
                "spool_deleted": spool_deleted,
            }
            completed = await store.complete_command(binding, response=response)
            return completed.response
        except (RuntimeStoreConflict, RuntimeStoreNotFound, ValueError) as exc:
            raise HTTPException(status_code=409, detail="artifact_upload_ack_conflict") from exc

    @app.post("/runs/{sid}/approve")
    async def approve_v2(
        sid: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="runtime.control", sid=sid
        )
        body = await _strict_json_body(request, V2ApproveBody)
        await _bound_body_session(
            claims,
            sid=sid,
            run_id=body.run_id,
            body_session_id=body.session_id,
            epoch=body.epoch,
        )
        raise HTTPException(
            status_code=501, detail="protocol-v2 approval control is not implemented"
        )

    async def _control_runtime(
        sid: str,
        request: Request,
        authorization: str | None,
        *,
        action: Literal["cancel", "terminate", "kill"],
    ) -> dict:
        claims = _authenticate_path(
            authorization, action="runtime.control", sid=sid
        )
        body = await _strict_json_body(request, ControlCommand)
        _enforce_binding(
            claims,
            run_id=body.run_id,
            session_id=body.session_id,
            epoch=body.epoch,
        )
        if (
            sid != body.session_id
            or body.target_kind != "runtime"
            or body.target_id != sid
            or body.action != action
        ):
            raise HTTPException(status_code=403, detail="binding_mismatch")

        binding = _binding(body, claims, action="runtime.control")
        known = await _inspect_command(binding)
        if known is not None and known.state == "completed":
            return known.response
        session = await store.get_session(sid)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session.run_id != body.run_id or body.epoch < session.epoch:
            raise HTTPException(status_code=403, detail="binding_mismatch")
        claim = await _claim_command(binding)
        if claim.is_retry and claim.receipt.state == "completed":
            return claim.receipt.response

        async with _session_lock(sid):
            known = await _inspect_command(binding)
            if known is not None and known.state == "completed":
                return known.response
            session = await store.get_session(sid)
            if session is None:
                raise HTTPException(status_code=404, detail="session not found")
            if session.run_id != body.run_id or body.epoch < session.epoch:
                raise HTTPException(status_code=403, detail="binding_mismatch")
            if session.state not in {"completed", "failed", "cancelled"}:
                try:
                    session = await store.transition_session(
                        sid,
                        expected_states=session.state,
                        new_state="cancelled",
                    )
                except (RuntimeStoreConflict, RuntimeStoreNotFound) as exc:
                    raise HTTPException(
                        status_code=409, detail="runtime_control_conflict"
                    ) from exc
            response = {
                "receipt_id": claim.receipt.receipt_id,
                "request_digest": binding.request_digest,
                "request_id": body.request_id,
                "run_id": body.run_id,
                "session_id": sid,
                "target_id": body.target_id,
                "action": body.action,
                "epoch": body.epoch,
                "status": "confirmed_stopped",
                "runtime_state": session.state,
                "runtime_shard_id": runtime_shard_id,
                "applied_at": datetime.now(UTC).isoformat(),
            }
            try:
                completed = await store.complete_command(
                    binding, response=response
                )
            except (RuntimeStoreConflict, RuntimeStoreNotFound) as exc:
                raise HTTPException(
                    status_code=409, detail="runtime_control_conflict"
                ) from exc
            return completed.response

    @app.post("/runs/{sid}/stop")
    async def stop_v2(
        sid: str,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="runtime.control", sid=sid
        )
        await _session_for_claims(sid, claims)
        raise HTTPException(
            status_code=501,
            detail="protocol-v2 stop cleanup is not a durable control action",
        )

    @app.post("/runs/{sid}/cancel")
    async def cancel_v2(
        sid: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        return await _control_runtime(
            sid, request, authorization, action="cancel"
        )

    @app.post("/runs/{sid}/terminate")
    async def terminate_v2(
        sid: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        return await _control_runtime(
            sid, request, authorization, action="terminate"
        )

    @app.post("/runs/{sid}/kill")
    async def kill_v2(
        sid: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        return await _control_runtime(
            sid, request, authorization, action="kill"
        )

    @app.get("/runs/{sid}/health")
    async def health_v2(
        sid: str,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ):
        claims = _authenticate_path(
            authorization, action="runtime.control", sid=sid
        )
        session = await _session_for_claims(sid, claims)
        return {
            "alive": session.state not in {"completed", "failed", "cancelled"},
            "cancelled": session.state == "cancelled",
            "state": session.state,
            "epoch": session.epoch,
            "runtime_shard_id": runtime_shard_id,
        }

    return app


def create_app(
    completer_factory=_completer,
    max_steps: int = 3,
    *,
    protocol_version: int = 1,
    runtime_store_path: str | None = None,
    service_auth: ServiceAuthConfig | Mapping[str, object] | None = None,
    runtime_spool_path: str | None = None,
    runtime_shard_id: str = "reference-0",
    artifact_ingest_base_url: str = "",
    max_active_sessions: int = 100,
    max_concurrent_turns: int = 4,
    max_queue_depth: int = 32,
    max_spool_bytes: int = 1024 * 1024 * 1024,
    max_artifact_bytes: int = 64 * 1024 * 1024,
    artifact_upload_timeout_seconds: float = 300.0,
    artifact_recovery_interval_seconds: float = 10.0,
    deployment_identity=None,
) -> FastAPI:
    if protocol_version == 1:
        return _create_v1_app(completer_factory, max_steps)
    if protocol_version != 2:
        raise ValueError(f"unsupported Runtime protocol version {protocol_version}")
    if not runtime_store_path:
        raise ValueError("protocol-v2 requires runtime_store_path")
    if service_auth is None:
        raise ValueError("protocol-v2 requires service_auth")
    return _create_v2_app(
        completer_factory=completer_factory,
        max_steps=max_steps,
        runtime_store_path=runtime_store_path,
        service_auth=service_auth,
        runtime_spool_path=runtime_spool_path,
        runtime_shard_id=runtime_shard_id,
        artifact_ingest_base_url=artifact_ingest_base_url,
        max_active_sessions=max_active_sessions,
        max_concurrent_turns=max_concurrent_turns,
        max_queue_depth=max_queue_depth,
        max_spool_bytes=max_spool_bytes,
        max_artifact_bytes=max_artifact_bytes,
        artifact_upload_timeout_seconds=artifact_upload_timeout_seconds,
        artifact_recovery_interval_seconds=artifact_recovery_interval_seconds,
        deployment_identity=deployment_identity,
    )


def create_entrypoint_app(
    environ: Mapping[str, str] | None = None,
) -> FastAPI:
    """Build the standalone process app from its isolated trust-plane env."""
    env = os.environ if environ is None else environ
    raw_version = env.get("LAB_RUNTIME_PROTOCOL_VERSION")
    if raw_version not in {"1", "2"}:
        raise ValueError(
            "LAB_RUNTIME_PROTOCOL_VERSION must explicitly be 1 or 2"
        )
    if raw_version == "1":
        return create_app(protocol_version=1)

    store_path = env.get("LAB_RUNTIME_STORE_PATH", "")
    issuer = env.get("LAB_RUNTIME_AUTH_ISSUER", "")
    audience = env.get("LAB_RUNTIME_AUTH_AUDIENCE", "")
    raw_keys = env.get("LAB_RUNTIME_AUTH_KEYS_JSON", "")
    if not store_path or not issuer or not audience or not raw_keys:
        raise ValueError(
            "protocol-v2 standalone Runtime requires store path, issuer, "
            "audience, and key ring"
        )
    if audience != "lab-runtime":
        raise ValueError("protocol-v2 standalone Runtime audience must be lab-runtime")
    try:
        keys = json.loads(raw_keys)
    except json.JSONDecodeError as exc:
        raise ValueError("LAB_RUNTIME_AUTH_KEYS_JSON must be a JSON object") from exc
    if not isinstance(keys, dict) or len(keys) < 2:
        raise ValueError(
            "protocol-v2 standalone Runtime requires current and next auth keys"
        )
    return create_app(
        protocol_version=2,
        runtime_store_path=store_path,
        runtime_spool_path=(
            env.get("LAB_RUNTIME_SPOOL_PATH") or f"{store_path}.artifacts"
        ),
        runtime_shard_id=env.get("LAB_RUNTIME_SHARD_ID", "reference-0"),
        artifact_ingest_base_url=env.get(
            "LAB_RUNTIME_ARTIFACT_INGEST_BASE_URL", ""
        ),
        service_auth={
            "issuer": issuer,
            "audience": audience,
            "keys": keys,
        },
    )


def _disabled_entrypoint_app() -> FastAPI:
    disabled = FastAPI(
        title="Simverse Lab reference runtime (not configured)", version="0"
    )

    @disabled.get("/livez", status_code=503)
    async def disabled_livez():
        return {"alive": False, "reason": "runtime_protocol_not_configured"}

    @disabled.get("/readyz", status_code=503)
    async def disabled_readyz():
        return {"ready": False, "reason": "runtime_protocol_not_configured"}

    return disabled


if __name__ == "__main__":
    try:
        app = create_entrypoint_app()
    except ValueError as exc:
        raise SystemExit(f"Runtime configuration error: {exc}") from exc
else:
    # Importing ``module:app`` must never silently select the legacy unauthenticated
    # protocol. The supported standalone entrypoint is ``python -m`` above.
    app = _disabled_entrypoint_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8900, log_level="warning")
