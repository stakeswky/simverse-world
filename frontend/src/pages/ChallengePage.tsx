import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import {
  getAgentActivityHistory,
  subscribeToAgentActivity,
} from '../webmcp/activity'
import { getChallengeStatus } from '../webmcp/challengeStatus'
import {
  registerChallengeStatusTool,
  type WebMcpRegistrationState,
} from '../webmcp/registerChallengeStatusTool'
import '../styles/challenge-page.css'

type PageRegistrationState = WebMcpRegistrationState | 'checking'

const registrationCopy: Record<PageRegistrationState, string> = {
  checking: 'Checking Site Tools support',
  registered: 'Site Tool ready',
  disabled: 'Disabled by build flag',
  unsupported: 'Site Tools unavailable in this browser',
  failed: 'Registration failed safely',
}

function readableActivityTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('en', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(date)
}

export function ChallengePage() {
  const status = getChallengeStatus()
  const [registrationState, setRegistrationState] = useState<PageRegistrationState>('checking')
  const subscribeToActivity = useCallback(
    (listener: () => void) => subscribeToAgentActivity(document, listener),
    [],
  )
  const getActivitySnapshot = useCallback(() => getAgentActivityHistory(document), [])
  const activities = useSyncExternalStore(
    subscribeToActivity,
    getActivitySnapshot,
    getActivitySnapshot,
  )

  useEffect(() => {
    let active = true

    void registerChallengeStatusTool()
      .then((state) => {
        if (active) setRegistrationState(state)
      })
      .catch(() => {
        if (active) setRegistrationState('failed')
      })

    return () => {
      active = false
    }
  }, [])

  return (
    <main className="challenge-page">
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

      <div className="challenge-shell">
        <section className="challenge-hero">
          <div>
            <p>SIMVERSE CIVIC COPILOT · WEBMCP PROBE</p>
            <h1>Co-govern a living AI town.</h1>
            <span>
              Humans and agents share one live page. The agent surfaces evidence; the human keeps final authority.
            </span>
          </div>
          <div className="challenge-tool-state" data-state={registrationState}>
            <i />
            {registrationCopy[registrationState]}
          </div>
        </section>

        <section className="challenge-status-grid" aria-label="Challenge Town status">
          <article><span>Town</span><strong>{status.town}</strong></article>
          <article><span>World time</span><strong>{status.world_time}</strong></article>
          <article><span>Scenario</span><strong>{status.scenario}</strong></article>
          <article><span>Tool version</span><strong>{status.tool_version}</strong></article>
          <article><span>Resettable</span><strong>{status.resettable ? 'Yes' : 'No'}</strong></article>
        </section>

        <div className="challenge-workspace">
          <section className="challenge-map-card" aria-labelledby="challenge-map-title">
            <header>
              <div><p>SHARED WORLD VIEW</p><h2 id="challenge-map-title">Challenge Town</h2></div>
              <span>Day-0 read-only probe</span>
            </header>
            <div className="challenge-map">
              <img src="/marketing/world-map.jpg" alt="Simverse town map" />
              <div className="challenge-harbor-marker" aria-label="Harbor district scenario marker">
                <i />
                <strong>Harbor district</strong>
                <span>Scenario ready for inspection</span>
              </div>
            </div>
            <footer>
              This probe returns fixed, non-sensitive status data. It does not call an LLM, read a token, or mutate production state.
            </footer>
          </section>

          <aside
            className="challenge-activity"
            aria-labelledby="agent-activity-title"
            aria-live="polite"
            aria-relevant="additions"
            role="log"
          >
            <header>
              <div><p>LIVE TOOL TRACE</p><h2 id="agent-activity-title">Agent Activity</h2></div>
              <span>{activities.length}</span>
            </header>

            {activities.length === 0 ? (
              <div className="challenge-activity-empty">
                <i />
                <strong>Waiting for a Site Tool call</strong>
                <span>Ask the agent to check the Challenge Town status.</span>
              </div>
            ) : (
              <ol>
                {activities.map((entry) => (
                  <li key={entry.id} data-outcome={entry.outcome}>
                    <span className="challenge-activity-icon" aria-hidden="true">
                      {entry.outcome === 'completed' ? '✓' : '×'}
                    </span>
                    <div>
                      <strong>{entry.toolName}</strong>
                      <span>
                        {entry.outcome === 'completed' ? 'Completed' : 'Failed safely'} in {entry.durationMs} ms
                      </span>
                    </div>
                    <time dateTime={entry.occurredAt}>{readableActivityTime(entry.occurredAt)}</time>
                  </li>
                ))}
              </ol>
            )}
          </aside>
        </div>
      </div>
    </main>
  )
}
