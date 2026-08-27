import type {
  ChallengeProjection,
  InvestigateInput,
} from '../../services/api/challenge'

interface DecisionFlowPanelProps {
  session: ChallengeProjection
  loading: boolean
  onInvestigate: (input: InvestigateInput) => Promise<void>
}

function shortHash(hash: string): string {
  return `${hash.slice(0, 19)}…`
}

export function DecisionFlowPanel({
  session,
  loading,
  onInvestigate,
}: DecisionFlowPanelProps) {
  const evidence = session.evidence
  const canInvestigate = session.state === 'INITIAL' || session.state === 'EVIDENCE_READY'

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
          <div data-active={index === 0 ? 'true' : 'false'} key={step}>
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

      {canInvestigate ? (
        <button
          type="button"
          disabled={loading}
          onClick={() => void onInvestigate({ budget_cap_sc: 300 })}
        >
          {evidence ? 'Rebuild Harbor evidence' : 'Investigate Harbor crisis'}
        </button>
      ) : null}
    </section>
  )
}
