import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { ChallengeHeader } from '../components/challenge/ChallengeHeader'
import { AgentActivityPanel } from '../components/challenge/AgentActivityPanel'
import { DecisionFlowPanel } from '../components/challenge/DecisionFlowPanel'
import { LivingWorldPanel } from '../components/challenge/LivingWorldPanel'
import { useChallengeStore } from '../stores/challengeStore'
import { ChallengeToolSurfaceManager } from '../webmcp/challengeToolSurfaceManager'
import { createChallengeTool } from '../webmcp/challengeTools'
import '../styles/challenge-page.css'

interface LegacyDiagnosticsState {
  toolName: string
  toolVersion: string
  registrationState: string
}

function LegacyDiagnostics() {
  const [diagnostics, setDiagnostics] = useState<LegacyDiagnosticsState | null>(null)

  useEffect(() => {
    let active = true
    const controller = new AbortController()

    void Promise.all([
      import('../webmcp/challengeStatus'),
      import('../webmcp/registerChallengeStatusTool'),
    ]).then(async ([statusModule, registrationModule]) => {
      const status = statusModule.getChallengeStatus()
      const registrationState = await registrationModule.registerChallengeStatusTool({
        signal: controller.signal,
      })
      if (active) {
        setDiagnostics({
          toolName: registrationModule.CHALLENGE_STATUS_TOOL_NAME,
          toolVersion: status.tool_version,
          registrationState,
        })
      }
    }).catch(() => {
      if (active) {
        setDiagnostics({
          toolName: 'Legacy status probe unavailable',
          toolVersion: 'unavailable',
          registrationState: 'failed',
        })
      }
    })

    return () => {
      active = false
      controller.abort()
    }
  }, [])

  return (
    <aside className="challenge-diagnostics" aria-label="Day-0 diagnostics">
      <span>DAY-0 DIAGNOSTICS</span>
      {diagnostics ? (
        <>
          <strong>{diagnostics.toolName}</strong>
          <code>{diagnostics.toolVersion}</code>
          <small>{diagnostics.registrationState}</small>
        </>
      ) : <strong>Loading diagnostic probe…</strong>}
    </aside>
  )
}

export function ChallengePage() {
  const location = useLocation()
  const session = useChallengeStore((state) => state.session)
  const loading = useChallengeStore((state) => state.loading)
  const activeToolNames = useChallengeStore((state) => state.activeToolNames)
  const registrationState = useChallengeStore((state) => state.registrationState)
  const error = useChallengeStore((state) => state.error)
  const initialize = useChallengeStore((state) => state.initialize)
  const investigate = useChallengeStore((state) => state.investigate)
  const preview = useChallengeStore((state) => state.preview)
  const approve = useChallengeStore((state) => state.approve)
  const revoke = useChallengeStore((state) => state.revoke)
  const verify = useChallengeStore((state) => state.verify)
  const reset = useChallengeStore((state) => state.reset)
  const setRegistrationState = useChallengeStore(
    (state) => state.setRegistrationState,
  )
  const [surfaceManager] = useState(() => new ChallengeToolSurfaceManager({
    enabled: import.meta.env.VITE_WEBMCP_ENABLED === 'true',
    createTool: (name) => createChallengeTool(name),
  }))
  const diagnosticsEnabled = new URLSearchParams(location.search).get('diagnostics') === '1'

  useEffect(() => {
    void initialize().catch(() => undefined)
  }, [initialize])

  useEffect(() => {
    if (
      session?.state !== 'APPROVED_ONCE'
      || session.approval_expires_at === null
    ) {
      return
    }
    const deadline = Date.parse(session.approval_expires_at)
    if (!Number.isFinite(deadline)) return
    const delay = Math.max(0, deadline - Date.now())
    const timeout = globalThis.setTimeout(() => {
      void initialize().catch(() => undefined)
    }, Math.min(delay, 2_147_483_647))
    return () => globalThis.clearTimeout(timeout)
  }, [initialize, session?.approval_expires_at, session?.state])

  useEffect(() => () => surfaceManager.destroy(), [surfaceManager])

  useEffect(() => {
    if (!session) return
    let active = true
    void surfaceManager.sync(session).then((state) => {
      if (active) setRegistrationState(state)
    })
    return () => {
      active = false
    }
  }, [session, setRegistrationState, surfaceManager])

  if (!session) {
    return (
      <main className="challenge-page">
        <header className="challenge-header challenge-header-minimal">
          <a className="challenge-brand" href="/" aria-label="Simverse World home">
            <span>S/</span> SIMVERSE
          </a>
          <nav aria-label="Challenge navigation">
            <a aria-current="page" href="/challenge">Challenge</a>
            <a href="/town">Live town</a>
          </nav>
        </header>
        <section className="challenge-session-boundary" aria-live="polite">
          {error ? (
            <div role="alert">
              <span>SESSION UNAVAILABLE</span>
              <h1>Challenge session is temporarily unavailable.</h1>
              <p>No internal error details were exposed. Retry the isolated anonymous session.</p>
              <button type="button" onClick={() => void initialize().catch(() => undefined)}>
                Retry session
              </button>
            </div>
          ) : (
            <div className="challenge-loading">
              <i />
              <h1>{loading ? 'Restoring Challenge Town…' : 'Preparing Challenge Town…'}</h1>
            </div>
          )}
        </section>
      </main>
    )
  }

  const canReset = ['VERIFIED', 'FAILED', 'EXPIRED'].includes(session.state)

  return (
    <main className="challenge-page">
      <div className="challenge-shell">
        <ChallengeHeader
          scenario={session.scenario_id}
          state={session.state}
          worldVersion={session.world_version}
          worldTime={session.world_time}
          budgetSc={session.budget_sc}
          activeToolNames={activeToolNames}
          activeToolCount={activeToolNames.length}
          registrationState={registrationState}
          expiresAt={session.expires_at}
          canReset={canReset}
          onReset={() => {
            void reset({ expected_generation: session.session_generation }).catch(
              () => undefined,
            )
          }}
        />

        {loading ? <div className="challenge-inline-loading">Syncing session projection…</div> : null}
        {error ? (
          <div className="challenge-inline-error" role="status">
            The last action failed safely. The current projection remains visible.
          </div>
        ) : null}

        <div className="challenge-workspace">
          <LivingWorldPanel world={session.world} evidence={session.evidence} />
          <DecisionFlowPanel
            session={session}
            loading={loading}
            onInvestigate={async (input) => {
              await investigate(input)
            }}
            onPreview={async (input) => {
              await preview(input)
            }}
            onApprove={async (input, event) => {
              await approve(input, event)
            }}
            onRevoke={async () => {
              await revoke()
            }}
            onVerify={async (input) => {
              await verify(input)
            }}
          />
          <AgentActivityPanel />
        </div>
        <p className="challenge-simulation-disclaimer">
          Forecast ranges come from a deterministic isolated simulation. They are
          not guaranteed outcomes and never change the production town.
        </p>
        {diagnosticsEnabled ? <LegacyDiagnostics /> : null}
      </div>
    </main>
  )
}
