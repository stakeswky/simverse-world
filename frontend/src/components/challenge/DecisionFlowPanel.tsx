import type {
  ApproveInput,
  ChallengeProjection,
  InvestigateInput,
  PreviewInput,
  VerifyInput,
} from '../../services/api/challenge'
import { HumanApprovalPanel } from './HumanApprovalPanel'
import { OutcomeComparison } from './OutcomeComparison'

interface DecisionFlowPanelProps {
  session: ChallengeProjection
  loading: boolean
  onInvestigate: (input: InvestigateInput) => Promise<void>
  onPreview: (input: PreviewInput) => Promise<void>
  onApprove: (
    input: ApproveInput,
    event: Pick<MouseEvent, 'isTrusted'>,
  ) => Promise<void>
  onRevoke: () => Promise<void>
  onVerify: (input: VerifyInput) => Promise<void>
}

function shortHash(hash: string): string {
  return `${hash.slice(0, 19)}…`
}

export function DecisionFlowPanel({
  session,
  loading,
  onInvestigate,
  onPreview,
  onApprove,
  onRevoke,
  onVerify,
}: DecisionFlowPanelProps) {
  const evidence = session.evidence
  const preview = session.preview
  const receipt = session.receipt
  const canInvestigate = session.state === 'INITIAL' || session.state === 'EVIDENCE_READY'
  const canPreview = evidence !== null && [
    'EVIDENCE_READY',
    'PREVIEW_READY',
    'APPROVED_ONCE',
  ].includes(session.state)
  const canVerify = session.state === 'COMMITTED' && receipt !== null
  const activeStep = {
    INITIAL: 0,
    EVIDENCE_READY: 1,
    PREVIEW_READY: 1,
    APPROVED_ONCE: 2,
    COMMITTED: 3,
    VERIFIED: 4,
    FAILED: 4,
    EXPIRED: 4,
  }[session.state]

  return (
    <section className="challenge-decision-flow" aria-labelledby="decision-flow-title">
      <header>
        <div>
          <p>HUMAN-LEGIBLE WORKFLOW</p>
          <h2 id="decision-flow-title">Decision Flow</h2>
        </div>
        <span>{session.state}</span>
      </header>

      <div className="challenge-flow-steps" aria-label="Challenge lifecycle">
        {['Investigate', 'Preview', 'Approve', 'Commit', 'Verify'].map((step, index) => (
          <div data-active={index === activeStep ? 'true' : 'false'} key={step}>
            <i>{index + 1}</i><span>{step}</span>
          </div>
        ))}
      </div>

      <div className="challenge-decision-meta">
        <span>World v{session.world_version}</span>
        <code>{shortHash(session.world_hash)}</code>
        <span>Budget cap {session.budget_sc} SC</span>
      </div>

      {evidence ? (
        <div className="challenge-evidence-snapshot">
          <div>
            <span>Evidence snapshot</span>
            <strong>Priority {evidence.priority_score}</strong>
          </div>
          <h3>{evidence.crisis_id}</h3>
          <p>{evidence.region_id} · World v{evidence.based_on_world_version}</p>
          <ul>
            {evidence.evidence.map((item) => (
              <li data-untrusted={item.untrusted ? 'true' : 'false'} key={item.source_id}>
                <span>{item.evidence_type}</span>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
                {item.untrusted ? <small>UNTRUSTED DATA</small> : null}
              </li>
            ))}
          </ul>
          <div className="challenge-constraints">
            <span>Enforced constraints</span>
            {evidence.enforced_constraints.map((constraint) => (
              <code key={constraint}>{constraint}</code>
            ))}
          </div>
        </div>
      ) : (
        <div className="challenge-evidence-empty">
          <strong>Evidence is not captured yet.</strong>
          <p>Read economic, resident, relationship, event, and map signals without mutating the world.</p>
        </div>
      )}

      {preview ? (
        <>
          <div className="challenge-intervention-preview">
          <header>
            <div>
              <span>Immutable World Diff</span>
              <strong>{preview.intervention_id}</strong>
            </div>
            <b>{session.approval_fingerprint ? 'Bound diff' : 'Review required'}</b>
          </header>
          <p>World v{preview.based_on_world_version} · {shortHash(preview.diff_hash)}</p>

          <section className="challenge-guaranteed-diff">
            <h3>Guaranteed on commit</h3>
            <div className="challenge-preview-totals">
              <strong>{preview.total_cost_sc} SC total</strong>
              <strong>{preview.remaining_budget_sc} SC remaining</strong>
            </div>
            <ul>
              <li>{preview.diff.resident_cash_changes.length} wage transfers</li>
              <li>{preview.diff.food_credit_changes.length} food credits</li>
              <li>{preview.diff.employer_claims_created.length} employer claims</li>
              <li>{preview.diff.events_created.length} mediation event</li>
            </ul>
            <div className="challenge-unchanged-invariants">
              <span>Explicitly unchanged</span>
              {preview.diff.explicitly_unchanged.map((invariant) => (
                <code data-testid="unchanged-invariant" key={invariant}>
                  {invariant}
                </code>
              ))}
            </div>
          </section>

          <section className="challenge-forecast-block">
            <h3>Forecast over 72h</h3>
            <p>{preview.forecast.seeds.length} fixed seeds · deterministic range</p>
            <dl>
              <div>
                <dt>High food risk</dt>
                <dd>{preview.forecast.high_food_risk_residents.min}–{preview.forecast.high_food_risk_residents.max}</dd>
              </div>
              <div>
                <dt>Social tension</dt>
                <dd>{preview.forecast.social_tension.min}–{preview.forecast.social_tension.max}</dd>
              </div>
              <div>
                <dt>Strike risk</dt>
                <dd>{preview.forecast.strike_risk_pct.min}–{preview.forecast.strike_risk_pct.max}%</dd>
              </div>
              <div>
                <dt>Stabilized</dt>
                <dd>{preview.forecast.stabilized_residents.min}–{preview.forecast.stabilized_residents.max}</dd>
              </div>
            </dl>
          </section>

          <section className="challenge-rejected-alternatives">
            <h3>Rejected alternatives</h3>
            {preview.rejected_alternatives.map((alternative) => (
              <article key={alternative.alternative_id}>
                <strong>{alternative.title}</strong>
                <code>{alternative.rejected_reason}</code>
                <small>
                  {alternative.total_cost_sc === null
                    ? 'Rejected by policy invariants'
                    : `${alternative.total_cost_sc} SC proposed`}
                </small>
              </article>
            ))}
          </section>
          </div>
          <HumanApprovalPanel
            key={`${session.state}:${preview.preview_id}`}
            session={session}
            onApprove={onApprove}
            onRevoke={onRevoke}
          />
        </>
      ) : null}

      {receipt ? (
        <section className="challenge-execution-receipt" aria-label="Execution Receipt">
          <header>
            <div>
              <span>Execution Receipt</span>
              <strong>{receipt.receipt_id}</strong>
            </div>
            <b>{receipt.approval_fingerprint}</b>
          </header>
          <p>{receipt.scenario_id} · Preview {receipt.preview_id}</p>
          <code>{receipt.session_generation}</code>
          <dl>
            <div>
              <dt>World</dt>
              <dd>World v{receipt.world_before_version} → v{receipt.world_after_version}</dd>
            </div>
            <div>
              <dt>Budget</dt>
              <dd>
                Budget {receipt.budget_before_sc} − {Math.abs(receipt.budget_delta_sc)} → {receipt.budget_after_sc} SC
              </dd>
            </div>
            <div>
              <dt>Approved diff</dt>
              <dd>{receipt.approved_diff_hash}</dd>
            </div>
            <div>
              <dt>World before</dt>
              <dd>{receipt.world_before_hash}</dd>
            </div>
            <div>
              <dt>World after</dt>
              <dd>{receipt.world_after_hash}</dd>
            </div>
          </dl>
          <section>
            <h3>Affected residents</h3>
            <ul>
              {receipt.affected_residents.map((residentId) => (
                <li data-testid="receipt-resident" key={residentId}>
                  <code>{residentId}</code>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3>Created events</h3>
            <ul>
              {receipt.created_events.map((eventId) => (
                <li key={eventId}><code>{eventId}</code></li>
              ))}
            </ul>
          </section>
          <section>
            <h3>Verified invariants</h3>
            <ul>
              {receipt.verified_invariants.map((invariant) => (
                <li data-testid="receipt-invariant" key={invariant}>
                  <code>{invariant}</code>
                </li>
              ))}
            </ul>
          </section>
        </section>
      ) : null}

      {session.verification ? (
        <OutcomeComparison
          key={session.verification.receipt_id}
          verification={session.verification}
        />
      ) : null}

      {canInvestigate || canPreview || canVerify ? (
        <div className="challenge-decision-actions">
          {canInvestigate ? (
            <button
              type="button"
              disabled={loading}
              onClick={() => void onInvestigate({ budget_cap_sc: 300 })}
            >
              {evidence ? 'Rebuild Harbor evidence' : 'Investigate Harbor crisis'}
            </button>
          ) : null}
          {canPreview ? (
            <button
              type="button"
              disabled={loading}
              onClick={() => void onPreview({
                crisis_id: 'harbor-wage-crisis',
                budget_cap_sc: 300,
              })}
            >
              {preview ? 'Rebuild intervention preview' : 'Preview intervention'}
            </button>
          ) : null}
          {canVerify && receipt ? (
            <button
              type="button"
              disabled={loading}
              onClick={() => void onVerify({
                receipt_id: receipt.receipt_id,
                advance_hours: 72,
              })}
            >
              Verify 72-hour outcome
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
