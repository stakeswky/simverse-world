import { useState, type MouseEvent as ReactMouseEvent } from 'react'

import type {
  ApproveInput,
  ChallengeProjection,
} from '../../services/api/challenge'
import { approveTrustedDiff } from './humanApprovalGate'

export interface HumanApprovalPanelProps {
  readonly session: ChallengeProjection
  readonly onApprove: (
    input: ApproveInput,
    event: Pick<MouseEvent, 'isTrusted'>,
  ) => Promise<void>
  readonly onRevoke: () => Promise<void>
}

function shortHash(hash: string): string {
  return `${hash.slice(0, 19)}…`
}

export function HumanApprovalPanel({
  session,
  onApprove,
  onRevoke,
}: HumanApprovalPanelProps) {
  const [reviewed, setReviewed] = useState(false)
  const [pending, setPending] = useState(false)
  const preview = session.preview

  if (
    preview === null
    || !['PREVIEW_READY', 'APPROVED_ONCE'].includes(session.state)
  ) {
    return null
  }

  const input: ApproveInput = {
    preview_id: preview.preview_id,
    expected_world_version: preview.based_on_world_version,
    diff_hash: preview.diff_hash,
  }

  const handleApprove = (event: ReactMouseEvent<HTMLButtonElement>) => {
    const nativeEvent = event.nativeEvent
    if (!reviewed || nativeEvent.isTrusted !== true || pending) return
    setPending(true)
    void approveTrustedDiff(reviewed, input, nativeEvent, onApprove)
      .catch(() => undefined)
      .finally(() => setPending(false))
  }

  if (session.state === 'APPROVED_ONCE') {
    return (
      <section className="challenge-human-approval" aria-label="One-time approval">
        <header>
          <div>
            <span>Approved once</span>
            <strong>{session.approval_fingerprint ?? 'Fingerprint unavailable'}</strong>
          </div>
          <b>World v{preview.based_on_world_version}</b>
        </header>
        <dl className="challenge-approval-binding">
          <div>
            <dt>Diff</dt>
            <dd>{shortHash(preview.diff_hash)}</dd>
          </div>
          <div>
            <dt>Expires</dt>
            <dd>{session.approval_expires_at ?? 'Expired'}</dd>
          </div>
        </dl>
        <p>The capability applies once to this exact server-bound diff.</p>
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            if (pending) return
            setPending(true)
            void onRevoke()
              .catch(() => undefined)
              .finally(() => setPending(false))
          }}
        >
          Revoke approval
        </button>
      </section>
    )
  }

  const diff = preview.diff
  return (
    <section className="challenge-human-approval" aria-label="Review World Diff">
      <header>
        <div>
          <span>Human approval required</span>
          <strong>Exact World Diff</strong>
        </div>
        <b>World v{preview.based_on_world_version}</b>
      </header>
      <p>Commit capability is not available to the agent.</p>
      <p>Review this exact diff to create a one-time approval.</p>

      <div className="challenge-approval-diff">
        <strong>
          Budget {diff.budget_before_sc} SC → {diff.budget_after_sc} SC
        </strong>
        <code>{preview.diff_hash}</code>

        <section>
          <h4>Resident cash</h4>
          <ul>
            {diff.resident_cash_changes.map((change) => (
              <li data-testid="approval-resident-change" key={change.resident_id}>
                <code>{change.resident_id}</code>
                <span>{change.before_sc} +{change.delta_sc} → {change.after_sc} SC</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h4>Food credit</h4>
          <ul>
            {diff.food_credit_changes.map((change) => (
              <li data-testid="approval-food-change" key={change.resident_id}>
                <code>{change.resident_id}</code>
                <span>{change.before_sc} +{change.delta_sc} → {change.after_sc} SC</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h4>Employer claims</h4>
          <ul>
            {diff.employer_claims_created.map((claim) => (
              <li data-testid="approval-employer-claim" key={claim.employer_id}>
                <code>{claim.employer_id}</code>
                <span>{claim.amount_sc} SC · {claim.status}</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h4>Events created</h4>
          <ul>
            {diff.events_created.map((createdEvent) => (
              <li key={createdEvent.event_id}>
                <code>{createdEvent.event_id}</code>
                <span>{createdEvent.event_type} · {createdEvent.region_id}</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h4>Explicitly unchanged</h4>
          <ul>
            {diff.explicitly_unchanged.map((invariant) => (
              <li data-testid="approval-unchanged" key={invariant}>
                <code>{invariant}</code>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <label className="challenge-approval-checkbox">
        <input
          type="checkbox"
          checked={reviewed}
          onChange={(event) => setReviewed(event.currentTarget.checked)}
        />
        <span>I reviewed this exact World Diff.</span>
      </label>
      <button
        type="button"
        disabled={!reviewed || pending}
        onClick={handleApprove}
      >
        Create one-time approval
      </button>
    </section>
  )
}
