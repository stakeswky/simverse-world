import type { ChallengeState } from '../../services/api/challenge'
import type { WebMcpRegistrationState } from '../../webmcp/registerChallengeStatusTool'

interface ChallengeHeaderProps {
  scenario: string
  state: ChallengeState
  worldVersion: number
  worldTime: string
  budgetSc: number
  activeToolNames: readonly string[]
  activeToolCount: number
  registrationState: WebMcpRegistrationState
  expiresAt: string
  canReset: boolean
  onReset: () => void
}

const REGISTRATION_COPY: Record<WebMcpRegistrationState, string> = {
  registered: 'Site Tools ready',
  disabled: 'Site Tools disabled',
  unsupported: 'Site Tools unavailable',
  failed: 'Site Tools failed safely',
}

export function ChallengeHeader({
  scenario,
  state,
  worldVersion,
  worldTime,
  budgetSc,
  activeToolNames,
  activeToolCount,
  registrationState,
  expiresAt,
  canReset,
  onReset,
}: ChallengeHeaderProps) {
  return (
    <>
      <header className="challenge-header">
        <a className="challenge-brand" href="/" aria-label="Simverse World home">
          <span>S/</span> SIMVERSE
        </a>
        <nav aria-label="Challenge navigation">
          <a aria-current="page" href="/challenge">Challenge</a>
          <a href="/town">Live town</a>
          <a href="/login">Enter world</a>
        </nav>
      </header>

      <section className="challenge-hero">
        <div>
          <p>SIMVERSE CIVIC COPILOT · ISOLATED TOWN</p>
          <h1>Co-govern a living AI town.</h1>
          <span>
            Evidence stays machine-readable, consequences stay visible, and final authority stays human.
          </span>
        </div>
        <div className="challenge-tool-state" data-state={registrationState}>
          <i />
          {REGISTRATION_COPY[registrationState]}
        </div>
      </section>

      <section className="challenge-status-grid" aria-label="Challenge session status">
        <article><span>Scenario</span><strong>{scenario}</strong></article>
        <article><span>State</span><strong>{state}</strong></article>
        <article><span>World</span><strong>World v{worldVersion}</strong></article>
        <article><span>World time</span><strong>{worldTime}</strong></article>
        <article><span>Budget</span><strong>Budget {budgetSc} SC</strong></article>
        <article className="challenge-tools-cell">
          <span>Tool surface</span>
          <strong>{activeToolCount} active {activeToolCount === 1 ? 'tool' : 'tools'}</strong>
          <small>{activeToolNames.length > 0 ? activeToolNames.join(' · ') : 'No active tools'}</small>
        </article>
        <article><span>Session</span><strong>Expires {expiresAt}</strong></article>
      </section>

      {canReset ? (
        <div className="challenge-reset-row">
          <span>This run is terminal and can be restored to the locked v7 fixture.</span>
          <button type="button" onClick={onReset}>Reset town</button>
        </div>
      ) : null}
    </>
  )
}
