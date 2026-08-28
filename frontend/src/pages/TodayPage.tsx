import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { LivingLoopDecisionCard } from '../components/living-loop/LivingLoopDecisionCard'
import {
  chooseLivingLoopDecision,
  getLivingLoopToday,
  markLivingLoopResultViewed,
  postProductEventsBatch,
  type LivingLoopChoice,
  type LivingLoopChoiceKey,
  type LivingLoopClientEventName,
  type LivingLoopTodayResponse,
} from '../services/api'
import '../styles/today-page.css'

interface ServerClockAnchor {
  serverMs: number
  clientMs: number
}

function livingLoopEnabled(): boolean {
  return import.meta.env.VITE_LIVING_LOOP_P0_ENABLED === 'true'
}

function createUuid(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }
  const bytes = new Uint8Array(16)
  globalThis.crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function safeJourneyPath(path: string | null | undefined, fallback: string): string {
  return path === '/play' || path === '/profile' || path === '/capsules' ? path : fallback
}

function projectionNow(anchor: ServerClockAnchor | null): number {
  if (!anchor || !Number.isFinite(anchor.serverMs)) return Date.now()
  return anchor.serverMs + (Date.now() - anchor.clientMs)
}

function useEntryPoint(): 'root' | 'direct' | 'return' {
  const location = useLocation()
  const state = location.state as { livingLoopEntryPoint?: string } | null
  if (state?.livingLoopEntryPoint === 'root') return 'root'
  return new URLSearchParams(location.search).get('entry') === 'return' ? 'return' : 'direct'
}

function TodayState({
  kind,
  onRetry,
  onEnterTown,
}: {
  kind: 'loading' | 'error' | 'disabled' | 'setup'
  onRetry?: () => void
  onEnterTown?: () => void
}) {
  const copy = {
    loading: {
      eyebrow: 'TODAY IS TAKING SHAPE',
      title: '正在整理今天的小镇动态',
      body: '正在读取你离开后发生的变化。',
    },
    error: {
      eyebrow: 'THE TOWN IS STILL THERE',
      title: '暂时无法整理今天的小镇动态',
      body: '你仍可以直接进入小镇，或稍后重新加载这份摘要。',
    },
    disabled: {
      eyebrow: 'COMING SOON',
      title: 'Living Loop 尚未开启',
      body: '今天页正在逐步开放，你仍可以照常进入原有小镇。',
    },
    setup: {
      eyebrow: 'ONE LAST STEP',
      title: '先完成居民设置',
      body: '选择你的玩家居民后，今天的事件才会与你建立联系。',
    },
  }[kind]

  return (
    <main className="today-page" aria-busy={kind === 'loading' ? 'true' : undefined}>
      <div className="today-page__shell today-page__shell--state">
        <section
          className="today-state-card"
          role={kind === 'loading' ? 'status' : kind === 'error' ? 'alert' : undefined}
          aria-label={kind === 'loading' ? copy.title : undefined}
        >
          <span className="today-state-card__orb" aria-hidden="true" />
          <p className="today-eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p>{copy.body}</p>
          <div className="today-state-card__actions">
            {kind === 'error' && onRetry && (
              <button type="button" onClick={onRetry}>重新加载</button>
            )}
            {kind === 'setup' ? (
              <Link to="/onboarding?next=%2Ftoday">选择我的居民</Link>
            ) : (
              <Link to="/play" onClick={onEnterTown}>进入小镇</Link>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}

export function TodayPage() {
  const enabled = livingLoopEnabled()
  const entryPoint = useEntryPoint()
  const [projection, setProjection] = useState<LivingLoopTodayResponse | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedChoice, setSelectedChoice] = useState<LivingLoopChoiceKey | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [, setClockTick] = useState(0)
  const [sessionId] = useState(createUuid)
  const requestControllerRef = useRef<AbortController | null>(null)
  const clockAnchorRef = useRef<ServerClockAnchor | null>(null)
  const submittingRef = useRef(false)
  const idempotencyRef = useRef<{ choice: LivingLoopChoiceKey; key: string } | null>(null)
  const sentRef = useRef(new Set<string>())
  const acknowledgedRef = useRef(new Set<string>())
  const dueRefreshRef = useRef(new Set<string>())

  const track = useCallback((
    eventName: LivingLoopClientEventName,
    properties: Record<string, string | number>,
  ) => {
    try {
      const request = postProductEventsBatch({
        events: [{
          event_id: createUuid(),
          session_id: sessionId,
          event_name: eventName,
          client_occurred_at: new Date().toISOString(),
          properties: { surface_version: 1, ...properties },
        }],
      })
      void Promise.resolve(request).catch(() => undefined)
    } catch {
      // Product telemetry is deliberately fail-open for every core action.
    }
  }, [sessionId])

  const trackOnce = useCallback((key: string, eventName: LivingLoopClientEventName, properties: Record<string, string | number>) => {
    if (sentRef.current.has(key)) return
    sentRef.current.add(key)
    track(eventName, properties)
  }, [track])

  const loadToday = useCallback(async (showLoading = true) => {
    if (!enabled) return
    requestControllerRef.current?.abort()
    const controller = new AbortController()
    requestControllerRef.current = controller
    if (showLoading) setLoading(true)
    setLoadError(null)

    try {
      const response = await getLivingLoopToday(controller.signal)
      if (controller.signal.aborted) return
      clockAnchorRef.current = {
        serverMs: Date.parse(response.server_now),
        clientMs: Date.now(),
      }
      setProjection(response)
      setSelectedChoice(null)
    } catch (reason: unknown) {
      if (controller.signal.aborted) return
      setLoadError(reason instanceof Error ? reason.message : 'Living Loop 暂时不可用')
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    if (!enabled) return
    void loadToday()
    return () => requestControllerRef.current?.abort()
  }, [enabled, loadToday])

  const decision = projection?.decision ?? null

  useEffect(() => {
    if (projection?.status !== 'ready' || !decision) return
    trackOnce('today-viewed', 'living_loop_today_viewed', { entry_point: entryPoint })
    if (decision.state === 'pending') {
      trackOnce(`decision:${decision.id}`, 'living_loop_decision_viewed', {
        decision_id: decision.id,
        scenario_key: decision.scenario_key,
        scenario_version: decision.scenario_version,
        decision_state: decision.state,
      })
    }
  }, [decision, entryPoint, projection?.status, trackOnce])

  useEffect(() => {
    if (!decision?.immediate_result || !decision.selected_choice) return
    trackOnce(`immediate:${decision.id}`, 'living_loop_immediate_result_viewed', {
      decision_id: decision.id,
      scenario_key: decision.scenario_key,
      scenario_version: decision.scenario_version,
      choice_key: decision.selected_choice,
    })
  }, [decision, trackOnce])

  useEffect(() => {
    if (!decision?.delayed_result || !decision.selected_choice) return

    trackOnce(`delayed:${decision.id}`, 'living_loop_delayed_result_viewed', {
      decision_id: decision.id,
      scenario_key: decision.scenario_key,
      scenario_version: decision.scenario_version,
      choice_key: decision.selected_choice,
    })

    if (decision.state !== 'result_ready' || acknowledgedRef.current.has(decision.id)) return
    acknowledgedRef.current.add(decision.id)
    void markLivingLoopResultViewed(decision.id)
      .then((updated) => {
        setProjection((current) => current ? { ...current, decision: updated } : current)
      })
      .catch(() => {
        acknowledgedRef.current.delete(decision.id)
        // The result remains readable; the idempotent acknowledgement can be retried on reload.
      })
  }, [decision, trackOnce])

  useEffect(() => {
    const previousResults = projection?.since_you_left.filter(
      (item) => item.kind === 'previous_result',
    ) ?? []
    for (const item of previousResults) {
      if (acknowledgedRef.current.has(item.id)) continue
      acknowledgedRef.current.add(item.id)
      void markLivingLoopResultViewed(item.id)
        .then((updated) => {
          if (!updated.selected_choice || !updated.delayed_result) return
          trackOnce(`delayed:${updated.id}`, 'living_loop_delayed_result_viewed', {
            decision_id: updated.id,
            scenario_key: updated.scenario_key,
            scenario_version: updated.scenario_version,
            choice_key: updated.selected_choice,
          })
        })
        .catch(() => {
          acknowledgedRef.current.delete(item.id)
          // A later aggregate reload can retry the idempotent acknowledgement.
        })
    }
  }, [projection?.since_you_left, trackOnce])

  useEffect(() => {
    if (!decision?.result_available_at || decision.delayed_result || decision.state !== 'chosen') return
    const resultAt = Date.parse(decision.result_available_at)
    if (!Number.isFinite(resultAt)) return
    const remaining = Math.max(0, resultAt - projectionNow(clockAnchorRef.current))
    const refreshKey = `${decision.id}:${decision.result_available_at}`
    if (dueRefreshRef.current.has(refreshKey)) return

    const timeout = window.setTimeout(() => {
      if (dueRefreshRef.current.has(refreshKey)) return
      dueRefreshRef.current.add(refreshKey)
      void loadToday(false)
    }, remaining)
    const ticker = window.setInterval(() => setClockTick((value) => value + 1), 1_000)

    return () => {
      window.clearTimeout(timeout)
      window.clearInterval(ticker)
    }
  }, [decision, loadToday])

  const remainingMs = decision?.result_available_at
    ? Math.max(0, Date.parse(decision.result_available_at) - projectionNow(clockAnchorRef.current))
    : null

  const handleSelect = (choice: LivingLoopChoice) => {
    if (submittingRef.current) return
    setSelectedChoice(choice.key)
    setSubmitError(null)
    idempotencyRef.current = null
    if (!decision) return
    track('living_loop_choice_previewed', {
      decision_id: decision.id,
      scenario_key: decision.scenario_key,
      scenario_version: decision.scenario_version,
      choice_key: choice.key,
    })
  }

  const handleConfirm = async () => {
    if (!decision || !selectedChoice || submittingRef.current || decision.state !== 'pending') return
    submittingRef.current = true
    setSubmitting(true)
    setSubmitError(null)
    if (!idempotencyRef.current || idempotencyRef.current.choice !== selectedChoice) {
      idempotencyRef.current = { choice: selectedChoice, key: createUuid() }
    }

    try {
      const updated = await chooseLivingLoopDecision(decision.id, {
        choice_key: selectedChoice,
        idempotency_key: idempotencyRef.current.key,
      })
      setProjection((current) => current ? { ...current, decision: updated } : current)
    } catch (reason: unknown) {
      setSubmitError(reason instanceof Error ? reason.message : '这个选择暂时无法保存，请重试。')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  if (!enabled) return <TodayState kind="disabled" />
  if (loading && !projection) {
    return <TodayState kind="loading" onEnterTown={() => track('living_loop_enter_town_clicked', { source: 'fallback' })} />
  }
  if (loadError && !projection) {
    return (
      <TodayState
        kind="error"
        onRetry={() => { void loadToday() }}
        onEnterTown={() => track('living_loop_enter_town_clicked', { source: 'fallback' })}
      />
    )
  }
  if (!projection || projection.status === 'feature_disabled' || !projection.experiment.enabled) {
    return <TodayState kind="disabled" />
  }
  if (projection.status === 'setup_required' || projection.setup_required || !projection.player_resident) {
    return <TodayState kind="setup" />
  }
  if (!decision) return <TodayState kind="error" onRetry={() => { void loadToday() }} />

  const townPath = safeJourneyPath(projection.journey.town_path, '/play')
  const profilePath = safeJourneyPath(projection.journey.profile_path, '/profile')
  const displayDate = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'UTC',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(new Date(projection.server_now))
  const latestReturnItem = projection.since_you_left[0]
  const consequenceSummary = decision.delayed_result
    ? '后果已经到达，可以现在查看'
    : decision.result_available_at
      ? `${new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'UTC',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).format(new Date(decision.result_available_at))} UTC 可查看`
      : '确认选择后显示服务端可查看时间'

  return (
    <main className="today-page">
      <div className="today-page__shell">
        <header className="today-header">
          <div>
            <p className="today-eyebrow">SIMVERSE / TODAY</p>
            <h1>今天的小镇</h1>
            <time dateTime={projection.server_now}>{displayDate} · UTC</time>
          </div>
          <div className="today-header__resident">
            <span aria-hidden="true">{projection.player_resident.name.slice(0, 1)}</span>
            <div><small>你的居民</small><strong>{projection.player_resident.name}</strong></div>
          </div>
          <Link to={townPath} onClick={() => track('living_loop_enter_town_clicked', { source: 'header' })}>
            进入小镇
          </Link>
        </header>

        {loadError && (
          <div className="today-refresh-warning" role="status">
            最新状态暂时无法刷新，已保留当前页面。
            <button type="button" onClick={() => { void loadToday(false) }}>重试</button>
          </div>
        )}

        <section className="today-glance" aria-label="今日一览">
          <article>
            <span>离开以后</span>
            <strong>{latestReturnItem?.title ?? '暂时没有新的回响'}</strong>
          </article>
          <article>
            <span>今天要处理</span>
            <strong>{decision.title}</strong>
          </article>
          <article>
            <span>后果时间</span>
            <strong>{consequenceSummary}</strong>
          </article>
        </section>

        <div className="today-page__main">
          <div className="today-page__primary">
            <section className="today-since" aria-labelledby="today-since-title">
              <div className="today-section-heading">
                <p className="today-eyebrow">WHILE YOU WERE AWAY</p>
                <h2 id="today-since-title">自你离开以后</h2>
              </div>
              {projection.since_you_left.length > 0 ? (
                <ol className="today-timeline">
                  {projection.since_you_left.map((item) => {
                    const link = safeJourneyPath(item.deep_link, '')
                    return (
                      <li key={`${item.kind}:${item.id}`}>
                        <span className="today-timeline__dot" aria-hidden="true" />
                        <div>
                          <time dateTime={item.occurred_at}>
                            {new Intl.DateTimeFormat('zh-CN', {
                              timeZone: 'UTC', hour: '2-digit', minute: '2-digit', hour12: false,
                            }).format(new Date(item.occurred_at))} UTC
                          </time>
                          <h3>{item.title}</h3>
                          <p>{item.summary}</p>
                          {link && (
                            <Link
                              to={link}
                              onClick={item.kind === 'digest'
                                ? () => track('living_loop_city_pulse_opened', { source: 'since_you_left', target: 'capsules' })
                                : undefined}
                            >
                              查看详情
                            </Link>
                          )}
                        </div>
                      </li>
                    )
                  })}
                </ol>
              ) : (
                <p className="today-empty">还没有新的回响。小镇会在生活继续时把变化留在这里。</p>
              )}
            </section>

            <LivingLoopDecisionCard
              decision={decision}
              selectedChoice={selectedChoice}
              submitting={submitting}
              submitError={submitError}
              remainingMs={remainingMs}
              onSelect={handleSelect}
              onConfirm={() => { void handleConfirm() }}
            />
          </div>

          <aside className="today-page__aside">
            <section className="today-pulse" aria-labelledby="today-pulse-title">
              <p className="today-eyebrow">CITY PULSE</p>
              <h2 id="today-pulse-title">城市脉搏</h2>
              {projection.city_pulse ? (
                <>
                  <time dateTime={projection.city_pulse.date}>{projection.city_pulse.date}</time>
                  <h3>{projection.city_pulse.title}</h3>
                  <p>{projection.city_pulse.summary}</p>
                  <Link
                    to={safeJourneyPath(projection.city_pulse.deep_link, '/capsules')}
                    onClick={() => track('living_loop_city_pulse_opened', { source: 'card', target: 'capsules' })}
                  >
                    打开{projection.city_pulse.title}
                  </Link>
                </>
              ) : (
                <p>今天的小镇仍在运转，新的村落日报还在整理中。</p>
              )}
            </section>

            <nav className="today-journey" aria-label="继续今天的旅程">
              <Link to={townPath} onClick={() => track('living_loop_enter_town_clicked', { source: 'secondary' })}>
                <span>继续探索</span><strong>进入小镇</strong>
              </Link>
              <Link to={profilePath} aria-label="查看我的居民">
                <span>居民档案</span><strong>查看我的居民</strong>
              </Link>
            </nav>
          </aside>
        </div>
      </div>
    </main>
  )
}
