import json
import hashlib
import re
from datetime import UTC, datetime, timedelta

import pytest

from app.challenge.errors import ChallengeDomainError, ChallengeErrorCode
from app.challenge.models import (
    ApprovalRecord,
    ApproveRequest,
    ChallengeState,
    CommitRequest,
    InvestigateRequest,
    PreviewRequest,
)
from app.challenge.repository import APPROVAL_TTL_SECONDS, ChallengeRepository
from app.challenge.service import ChallengeService

pytestmark = pytest.mark.anyio

NOW = datetime(2042, 6, 12, 8, tzinfo=UTC)


async def _preview_ready(service: ChallengeService, session_id: str):
    await service.investigate(
        session_id, InvestigateRequest(budget_cap_sc=300)
    )
    return await service.preview(
        session_id,
        PreviewRequest(crisis_id="harbor-wage-crisis", budget_cap_sc=300),
    )


async def _approved_once(service: ChallengeService, session_id: str):
    previewed = await _preview_ready(service, session_id)
    preview = previewed.projection.preview
    assert preview is not None
    approved = await service.approve(
        session_id,
        ApproveRequest(
            preview_id=preview.preview_id,
            expected_world_version=preview.based_on_world_version,
            diff_hash=preview.diff_hash,
        ),
    )
    assert approved.approval_id is not None
    return approved, preview


async def test_preview_rebuild_atomically_invalidates_server_side_approval() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    await service.investigate(
        created.session_id, InvestigateRequest(budget_cap_sc=300)
    )
    initial_preview = await service.preview(
        created.session_id,
        PreviewRequest(crisis_id="harbor-wage-crisis", budget_cap_sc=300),
    )
    assert initial_preview.projection.preview is not None
    old_preview = initial_preview.projection.preview
    old_world_hash = initial_preview.projection.world_hash
    approval = ApprovalRecord(
        approval_id="approval-server-only-secret",
        session_generation=initial_preview.projection.session_generation,
        preview_id=old_preview.preview_id,
        diff_hash=old_preview.diff_hash,
        world_version=7,
        status="APPROVED_ONCE",
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=APPROVAL_TTL_SECONDS),
    )
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    await repository.save_session(
        created.session_id,
        stored.model_copy(
            update={
                "state": ChallengeState.APPROVED_ONCE,
                "active_approval_id": approval.approval_id,
                "approval_fingerprint": "fingerprint-secret",
                "approval_expires_at": approval.expires_at,
            }
        ),
    )
    await repository.save_approval(approval)

    rebuilt = await service.preview(
        created.session_id,
        PreviewRequest(crisis_id="harbor-wage-crisis", budget_cap_sc=300),
    )

    assert rebuilt.projection.state is ChallengeState.PREVIEW_READY
    assert rebuilt.projection.preview is not None
    assert rebuilt.projection.preview.preview_id != old_preview.preview_id
    assert rebuilt.projection.preview.diff_hash != old_preview.diff_hash
    assert rebuilt.projection.world_hash == old_world_hash
    invalidated = await repository.load_approval(approval.approval_id)
    assert invalidated is not None
    assert invalidated.status == "INVALIDATED"
    after = await repository.load_session(created.session_id)
    assert after is not None
    assert after.active_approval_id is None
    assert after.approval_fingerprint is None
    assert after.approval_expires_at is None
    audit_json = json.dumps(
        [event.model_dump(mode="json") for event in after.audit_events]
    )
    assert approval.approval_id not in audit_json
    assert "fingerprint-secret" not in audit_json
    assert after.csrf_token not in audit_json


async def test_approve_recomputes_and_binds_a_server_only_capability() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    previewed = await _preview_ready(service, created.session_id)
    preview = previewed.projection.preview
    assert preview is not None
    before_world_hash = previewed.projection.world_hash

    approved = await service.approve(
        created.session_id,
        ApproveRequest(
            preview_id=preview.preview_id,
            expected_world_version=preview.based_on_world_version,
            diff_hash=preview.diff_hash,
        ),
    )

    assert approved.approval_id is not None
    assert len(approved.approval_id) >= 43
    expected_fingerprint = "appr-" + hashlib.sha256(
        approved.approval_id.encode()
    ).hexdigest()[:4].upper()
    assert approved.projection.state is ChallengeState.APPROVED_ONCE
    assert approved.projection.tool_surface == ["simverse_commit_approved"]
    assert approved.projection.approval_fingerprint == expected_fingerprint
    assert re.fullmatch(r"appr-[0-9A-F]{4}", expected_fingerprint)
    assert approved.projection.approval_expires_at == (
        NOW + timedelta(seconds=APPROVAL_TTL_SECONDS)
    )
    assert approved.projection.world_hash == before_world_hash
    projection_json = json.dumps(approved.projection.model_dump(mode="json"))
    assert approved.approval_id not in projection_json
    assert "active_approval_id" not in projection_json

    stored = await repository.load_session(created.session_id)
    capability = await repository.load_approval(approved.approval_id)
    assert stored is not None
    assert capability is not None
    assert stored.active_approval_id == approved.approval_id
    assert capability.session_generation == stored.session_generation
    assert capability.preview_id == preview.preview_id
    assert capability.diff_hash == preview.diff_hash
    assert capability.world_version == 7
    assert capability.status == "APPROVED_ONCE"
    assert capability.created_at == NOW
    assert capability.expires_at == NOW + timedelta(seconds=90)


async def test_approve_without_preview_is_rejected_without_capability() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.approve(
            created.session_id,
            ApproveRequest(
                preview_id="missing-preview",
                expected_world_version=7,
                diff_hash="sha256:" + "a" * 64,
            ),
        )

    assert rejected.value.code is ChallengeErrorCode.INVALID_STATE_TRANSITION
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.active_approval_id is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("preview_id", "wrong-preview"),
        ("expected_world_version", 8),
        ("diff_hash", "sha256:" + "f" * 64),
    ],
)
async def test_approve_rejects_each_request_binding_mismatch(
    field: str,
    value: str | int,
) -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    previewed = await _preview_ready(service, created.session_id)
    preview = previewed.projection.preview
    assert preview is not None
    payload: dict[str, str | int] = {
        "preview_id": preview.preview_id,
        "expected_world_version": preview.based_on_world_version,
        "diff_hash": preview.diff_hash,
    }
    payload[field] = value

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.approve(created.session_id, ApproveRequest(**payload))

    assert rejected.value.code is ChallengeErrorCode.APPROVAL_MISMATCH
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.state is ChallengeState.PREVIEW_READY
    assert stored.active_approval_id is None


async def test_approve_detects_a_tampered_stored_preview_by_server_rebuild() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    await _preview_ready(service, created.session_id)
    stored = await repository.load_session(created.session_id)
    assert stored is not None and stored.preview is not None
    tampered_hash = "sha256:" + "f" * 64
    tampered_preview = stored.preview.model_copy(
        update={"diff_hash": tampered_hash},
        deep=True,
    )
    await repository.save_session(
        created.session_id,
        stored.model_copy(update={"preview": tampered_preview}, deep=True),
    )

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.approve(
            created.session_id,
            ApproveRequest(
                preview_id=tampered_preview.preview_id,
                expected_world_version=7,
                diff_hash=tampered_hash,
            ),
        )

    assert rejected.value.code is ChallengeErrorCode.PREVIEW_STALE


async def test_approve_rejects_changed_world_and_cross_session_preview() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    first = await service.create_or_resume(None)
    second = await service.create_or_resume(None)
    first_previewed = await _preview_ready(service, first.session_id)
    second_previewed = await _preview_ready(service, second.session_id)
    first_preview = first_previewed.projection.preview
    second_preview = second_previewed.projection.preview
    assert first_preview is not None and second_preview is not None

    with pytest.raises(ChallengeDomainError) as cross_session:
        await service.approve(
            second.session_id,
            ApproveRequest(
                preview_id=first_preview.preview_id,
                expected_world_version=7,
                diff_hash=first_preview.diff_hash,
            ),
        )
    assert cross_session.value.code is ChallengeErrorCode.APPROVAL_MISMATCH

    await repository.mutate_session(
        first.session_id,
        lambda session, now: session.model_copy(
            update={
                "world": session.world.model_copy(
                    update={"world_version": 8}, deep=True
                )
            },
            deep=True,
        ),
    )
    with pytest.raises(ChallengeDomainError) as stale_world:
        await service.approve(
            first.session_id,
            ApproveRequest(
                preview_id=first_preview.preview_id,
                expected_world_version=7,
                diff_hash=first_preview.diff_hash,
            ),
        )
    assert stale_world.value.code is ChallengeErrorCode.STALE_WORLD_VERSION


async def test_approval_expiry_atomically_restores_preview_and_tombstone() -> None:
    current = {"now": NOW}
    repository = ChallengeRepository(clock=lambda: current["now"])
    service = ChallengeService(repository=repository, clock=lambda: current["now"])
    created = await service.create_or_resume(None)
    previewed = await _preview_ready(service, created.session_id)
    preview = previewed.projection.preview
    assert preview is not None
    approved = await service.approve(
        created.session_id,
        ApproveRequest(
            preview_id=preview.preview_id,
            expected_world_version=7,
            diff_hash=preview.diff_hash,
        ),
    )
    assert approved.approval_id is not None

    current["now"] += timedelta(seconds=APPROVAL_TTL_SECONDS + 1)
    expired = await service.get_session(created.session_id)

    assert expired.projection.state is ChallengeState.PREVIEW_READY
    assert expired.projection.approval_fingerprint is None
    assert expired.projection.approval_expires_at is None
    tombstone = await repository.load_approval(approved.approval_id)
    assert tombstone is not None
    assert tombstone.status == "EXPIRED"
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    expiry_audits = [
        event for event in stored.audit_events
        if event.reason_code == ChallengeErrorCode.APPROVAL_EXPIRED.value
    ]
    assert len(expiry_audits) == 1
    assert expiry_audits[0].state_before is ChallengeState.APPROVED_ONCE
    assert expiry_audits[0].state_after is ChallengeState.PREVIEW_READY


async def test_revoke_writes_tombstone_and_clears_active_capability() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    previewed = await _preview_ready(service, created.session_id)
    preview = previewed.projection.preview
    assert preview is not None
    approved = await service.approve(
        created.session_id,
        ApproveRequest(
            preview_id=preview.preview_id,
            expected_world_version=7,
            diff_hash=preview.diff_hash,
        ),
    )
    assert approved.approval_id is not None

    revoked = await service.revoke(created.session_id)

    assert revoked.projection.state is ChallengeState.PREVIEW_READY
    assert revoked.projection.approval_fingerprint is None
    assert revoked.projection.approval_expires_at is None
    tombstone = await repository.load_approval(approved.approval_id)
    assert tombstone is not None
    assert tombstone.status == "REVOKED"
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.active_approval_id is None
    assert any(event.action == "revoke" for event in stored.audit_events)


async def test_commit_consumes_bound_approval_and_receipt_in_one_transition() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    approved, preview = await _approved_once(service, created.session_id)
    before_hash = approved.projection.world_hash

    committed = await service.commit(
        created.session_id,
        approved.approval_id,
        CommitRequest(
            preview_id=preview.preview_id,
            expected_world_version=7,
            diff_hash=preview.diff_hash,
        ),
    )

    assert committed.projection.state is ChallengeState.COMMITTED
    assert committed.projection.world_version == 8
    assert committed.projection.budget_sc == 60
    assert committed.projection.world_hash != before_hash
    assert committed.projection.receipt is not None
    assert committed.projection.receipt.world_before_version == 7
    assert committed.projection.receipt.world_after_version == 8
    assert committed.projection.receipt.approved_diff_hash == preview.diff_hash
    assert committed.projection.receipt.approval_fingerprint == (
        approved.projection.approval_fingerprint
    )
    stored = await repository.load_session(created.session_id)
    tombstone = await repository.load_approval(approved.approval_id)
    assert stored is not None and tombstone is not None
    assert stored.active_approval_id is None
    assert stored.approval_fingerprint is None
    assert stored.approval_expires_at is None
    assert stored.receipt == committed.projection.receipt
    assert tombstone.status == "CONSUMED"
    commit_events = [event for event in stored.audit_events if event.action == "commit"]
    assert len(commit_events) == 1
    assert commit_events[0].world_version_before == 7
    assert commit_events[0].world_version_after == 8


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("preview_id", "wrong-preview", ChallengeErrorCode.APPROVAL_MISMATCH),
        ("diff_hash", "sha256:" + "f" * 64, ChallengeErrorCode.APPROVAL_MISMATCH),
        ("expected_world_version", 8, ChallengeErrorCode.STALE_WORLD_VERSION),
    ],
)
async def test_commit_rejects_each_request_binding_before_any_world_change(
    field: str,
    value: str | int,
    expected_code: ChallengeErrorCode,
) -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    approved, preview = await _approved_once(service, created.session_id)
    payload: dict[str, str | int] = {
        "preview_id": preview.preview_id,
        "expected_world_version": 7,
        "diff_hash": preview.diff_hash,
    }
    payload[field] = value

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.commit(
            created.session_id,
            approved.approval_id,
            CommitRequest(**payload),
        )

    assert rejected.value.code is expected_code
    stored = await repository.load_session(created.session_id)
    capability = await repository.load_approval(approved.approval_id)
    assert stored is not None and capability is not None
    assert stored.state is ChallengeState.APPROVED_ONCE
    assert stored.world.world_version == 7
    assert stored.world.budget_sc == 300
    assert stored.receipt is None
    assert capability.status == "APPROVED_ONCE"


async def test_commit_rejects_cookie_for_another_session_and_missing_record() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    first = await service.create_or_resume(None)
    second = await service.create_or_resume(None)
    first_approved, first_preview = await _approved_once(service, first.session_id)
    second_approved, _ = await _approved_once(service, second.session_id)

    with pytest.raises(ChallengeDomainError) as cross_session:
        await service.commit(
            first.session_id,
            second_approved.approval_id,
            CommitRequest(
                preview_id=first_preview.preview_id,
                expected_world_version=7,
                diff_hash=first_preview.diff_hash,
            ),
        )
    assert cross_session.value.code is ChallengeErrorCode.APPROVAL_MISMATCH

    with pytest.raises(ChallengeDomainError) as missing:
        await service.commit(
            first.session_id,
            "missing-approval-record",
            CommitRequest(
                preview_id=first_preview.preview_id,
                expected_world_version=7,
                diff_hash=first_preview.diff_hash,
            ),
        )
    assert missing.value.code is ChallengeErrorCode.APPROVAL_REQUIRED
    stored = await repository.load_session(first.session_id)
    capability = await repository.load_approval(first_approved.approval_id)
    assert stored is not None and capability is not None
    assert stored.state is ChallengeState.APPROVED_ONCE
    assert capability.status == "APPROVED_ONCE"


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        ("EXPIRED", ChallengeErrorCode.APPROVAL_EXPIRED),
        ("REVOKED", ChallengeErrorCode.APPROVAL_REVOKED),
        ("INVALIDATED", ChallengeErrorCode.APPROVAL_MISMATCH),
        ("CONSUMED", ChallengeErrorCode.APPROVAL_REPLAYED),
    ],
)
async def test_commit_rejects_terminal_approval_status(
    status: str,
    expected_code: ChallengeErrorCode,
) -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    approved, preview = await _approved_once(service, created.session_id)
    capability = await repository.load_approval(approved.approval_id)
    assert capability is not None
    await repository.save_approval(capability.model_copy(update={"status": status}))

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.commit(
            created.session_id,
            approved.approval_id,
            CommitRequest(
                preview_id=preview.preview_id,
                expected_world_version=7,
                diff_hash=preview.diff_hash,
            ),
        )

    assert rejected.value.code is expected_code
    stored = await repository.load_session(created.session_id)
    assert stored is not None
    assert stored.world.world_version == 7
    assert stored.receipt is None


@pytest.mark.parametrize("tamper", ["generation", "preview", "world_version"])
async def test_commit_rejects_stale_server_side_approval_binding(tamper: str) -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    approved, preview = await _approved_once(service, created.session_id)
    capability = await repository.load_approval(approved.approval_id)
    assert capability is not None
    updates = {
        "generation": {"session_generation": "old-generation"},
        "preview": {"preview_id": "old-preview"},
        "world_version": {"world_version": 6},
    }
    await repository.save_approval(capability.model_copy(update=updates[tamper]))

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.commit(
            created.session_id,
            approved.approval_id,
            CommitRequest(
                preview_id=preview.preview_id,
                expected_world_version=7,
                diff_hash=preview.diff_hash,
            ),
        )

    assert rejected.value.code is ChallengeErrorCode.APPROVAL_MISMATCH


async def test_commit_rebuilds_preview_and_rejects_tampered_server_hash() -> None:
    repository = ChallengeRepository(clock=lambda: NOW)
    service = ChallengeService(repository=repository, clock=lambda: NOW)
    created = await service.create_or_resume(None)
    approved, preview = await _approved_once(service, created.session_id)
    stored = await repository.load_session(created.session_id)
    capability = await repository.load_approval(approved.approval_id)
    assert stored is not None and stored.preview is not None
    assert capability is not None
    tampered_hash = "sha256:" + "f" * 64
    await repository.save_session(
        created.session_id,
        stored.model_copy(
            update={
                "preview": stored.preview.model_copy(
                    update={"diff_hash": tampered_hash}, deep=True
                )
            },
            deep=True,
        ),
    )
    await repository.save_approval(
        capability.model_copy(update={"diff_hash": tampered_hash})
    )

    with pytest.raises(ChallengeDomainError) as rejected:
        await service.commit(
            created.session_id,
            approved.approval_id,
            CommitRequest(
                preview_id=preview.preview_id,
                expected_world_version=7,
                diff_hash=tampered_hash,
            ),
        )

    assert rejected.value.code is ChallengeErrorCode.PREVIEW_STALE
    unchanged = await repository.load_session(created.session_id)
    assert unchanged is not None
    assert unchanged.world.world_version == 7
    assert unchanged.receipt is None
