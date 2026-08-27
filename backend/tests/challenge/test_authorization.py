import json
from datetime import UTC, datetime, timedelta

import pytest

from app.challenge.models import (
    ApprovalRecord,
    ChallengeState,
    InvestigateRequest,
    PreviewRequest,
)
from app.challenge.repository import APPROVAL_TTL_SECONDS, ChallengeRepository
from app.challenge.service import ChallengeService

pytestmark = pytest.mark.anyio

NOW = datetime(2042, 6, 12, 8, tzinfo=UTC)


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
