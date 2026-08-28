import '@testing-library/jest-dom/vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'

const livingLoopApi = vi.hoisted(() => ({
  getLivingLoopToday: vi.fn(),
  chooseLivingLoopDecision: vi.fn(),
  markLivingLoopResultViewed: vi.fn(),
  postProductEventsBatch: vi.fn(),
}))

vi.mock('../services/api', () => livingLoopApi)

import { TodayPage } from './TodayPage'

const DECISION_ID = 'afe0c239-bd26-401c-80cf-97d4fc9953bc'

const choices = [
  {
    key: 'public_support',
    label: '公开站出来支持工人',
    summary: '直接表明立场，立即回应工人的诉求。',
    tradeoffs: ['工人信任 +8', '管理方信任 -5', '城市信用 +2'],
  },
  {
    key: 'private_mediation',
    label: '先组织一场私下调解',
    summary: '先让双方在不公开升级冲突的情况下谈判。',
    tradeoffs: ['工人信任 +3', '管理方信任 +3', '城市信用 +1'],
  },
  {
    key: 'collect_evidence',
    label: '先核实排班和欠薪证据',
    summary: '先建立能够支持后续行动的事实基础。',
    tradeoffs: ['工人信任 +2', '管理方信任 0', '城市信用 +4'],
  },
] as const

const pendingDecision = {
  id: DECISION_ID,
  scenario_key: 'harbor_wage_dispute_v1',
  scenario_version: 1,
  state: 'pending',
  title: '港口欠薪风波',
  context: '玩家居民在港口发现三名工人连续两周没有拿到完整工资。',
  stakes: ['港口不能停摆', '工人耐心接近极限'],
  choices,
  selected_choice: null,
  immediate_result: null,
  result_available_at: null,
  delayed_result: null,
}

const immediateResult = {
  title: '决定已经保存',
  summary: '你组织了一场私下调解，双方暂时回到了谈判桌前。',
  effects: {
    worker_trust_delta: 3,
    management_trust_delta: 3,
    city_credit_delta: 1,
  },
}

const delayedResult = {
  title: '港口传来新进展',
  summary: '双方同意建立临时发薪时间表，但历史欠款仍未解决。',
}

function chosenDecision(resultAvailableAt = '2026-08-28T20:00:00Z') {
  return {
    ...pendingDecision,
    state: 'chosen',
    selected_choice: 'private_mediation',
    immediate_result: immediateResult,
    result_available_at: resultAvailableAt,
  }
}

function readyDecision(state: 'result_ready' | 'result_viewed' = 'result_ready') {
  return {
    ...chosenDecision('2026-08-28T12:00:00Z'),
    state,
    delayed_result: delayedResult,
  }
}

function readyProjection(decision: typeof pendingDecision | ReturnType<typeof chosenDecision> | ReturnType<typeof readyDecision> = pendingDecision) {
  return {
    experiment: { key: 'living_loop_p0', enabled: true },
    server_now: '2026-08-28T12:00:00Z',
    status: 'ready',
    setup_required: false,
    player_resident: {
      id: 'resident-1',
      slug: 'player-resident',
      name: '玩家居民',
      district: 'harbor',
      sprite_key: '埃迪',
    },
    since_you_left: [
      {
        id: 'result-1',
        kind: 'previous_result',
        title: '昨天的选择有了结果',
        summary: '居民代表已经抵达港口。',
        occurred_at: '2026-08-28T08:00:00Z',
        deep_link: null,
      },
      {
        id: 'notification-1',
        kind: 'notification',
        title: '一位居民给你留了消息',
        summary: '工程区今天格外忙碌。',
        occurred_at: '2026-08-28T09:00:00Z',
        deep_link: '/profile',
      },
    ],
    city_pulse: {
      title: '今日村落日报',
      summary: '港口、学园与产品街区都出现了新的讨论。',
      date: '2026-08-28',
      deep_link: '/capsules',
      is_fallback: false,
    },
    decision,
    journey: { town_path: '/play', profile_path: '/profile' },
  }
}

const disabledProjection = {
  experiment: { key: 'living_loop_p0', enabled: false },
  server_now: '2026-08-28T12:00:00Z',
  status: 'feature_disabled',
  setup_required: false,
  player_resident: null,
  since_you_left: [],
  city_pulse: null,
  decision: null,
  journey: { town_path: '/play', profile_path: '/profile' },
}

const setupProjection = {
  ...disabledProjection,
  experiment: { key: 'living_loop_p0', enabled: true },
  status: 'setup_required',
  setup_required: true,
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="today-location">{`${location.pathname}${location.search}${location.hash}`}</output>
}

function renderToday(path = '/today') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <TodayPage />
      <LocationProbe />
    </MemoryRouter>,
  )
}

function eventNames(): string[] {
  return livingLoopApi.postProductEventsBatch.mock.calls.flatMap(([batch]) => (
    (batch as { events?: Array<{ event_name?: string }> }).events?.map((event) => event.event_name ?? '') ?? []
  ))
}

beforeEach(() => {
  vi.stubEnv('VITE_LIVING_LOOP_P0_ENABLED', 'true')
  livingLoopApi.getLivingLoopToday.mockReset().mockResolvedValue(readyProjection())
  livingLoopApi.chooseLivingLoopDecision.mockReset().mockResolvedValue(chosenDecision())
  livingLoopApi.markLivingLoopResultViewed.mockReset().mockResolvedValue(readyDecision('result_viewed'))
  livingLoopApi.postProductEventsBatch.mockReset().mockResolvedValue({ accepted: 1, duplicates: 0 })
})

afterEach(() => {
  cleanup()
  vi.unstubAllEnvs()
  vi.useRealTimers()
})

describe('TodayPage states and consequence flow', () => {
  it('renders a stable accessible loading state while the aggregate request is pending', () => {
    livingLoopApi.getLivingLoopToday.mockReturnValue(new Promise(() => undefined))

    renderToday()

    const main = screen.getByRole('main')
    expect(main).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('status', { name: '正在整理今天的小镇动态' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '进入小镇' })).toHaveAttribute('href', '/play')
  })

  it('shows a retryable error without trapping the player, then recovers', async () => {
    livingLoopApi.getLivingLoopToday
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(readyProjection())

    renderToday()

    expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法整理今天的小镇动态')
    expect(screen.getByRole('link', { name: '进入小镇' })).toHaveAttribute('href', '/play')

    fireEvent.click(screen.getByRole('button', { name: '重新加载' }))

    expect(await screen.findByRole('heading', { name: '港口欠薪风波' })).toBeInTheDocument()
    expect(livingLoopApi.getLivingLoopToday).toHaveBeenCalledTimes(2)
  })

  it('uses a local feature-disabled state without calling the backend when the frontend flag is off', () => {
    vi.stubEnv('VITE_LIVING_LOOP_P0_ENABLED', 'false')

    renderToday()

    expect(screen.getByRole('heading', { name: 'Living Loop 尚未开启' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '进入小镇' })).toHaveAttribute('href', '/play')
    expect(livingLoopApi.getLivingLoopToday).not.toHaveBeenCalled()
  })

  it('degrades safely when the backend reports the feature disabled', async () => {
    livingLoopApi.getLivingLoopToday.mockResolvedValue(disabledProjection)

    renderToday()

    expect(await screen.findByRole('heading', { name: 'Living Loop 尚未开启' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '进入小镇' })).toHaveAttribute('href', '/play')
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(eventNames()).toEqual([])
  })

  it('sends a setup-required user to onboarding while preserving /today', async () => {
    livingLoopApi.getLivingLoopToday.mockResolvedValue(setupProjection)

    renderToday()

    expect(await screen.findByRole('heading', { name: '先完成居民设置' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '选择我的居民' })).toHaveAttribute(
      'href',
      '/onboarding?next=%2Ftoday',
    )
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(eventNames()).toEqual([])
  })

  it('renders the three consequence-first regions, three native choices, and safe journey links', async () => {
    renderToday()

    expect(await screen.findByRole('heading', { name: '自你离开以后' })).toBeInTheDocument()
    expect(screen.getByText('昨天的选择有了结果')).toBeInTheDocument()
    expect(screen.getByText('一位居民给你留了消息')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: '今天最重要的一件事' })).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(3)
    expect(screen.getByRole('heading', { name: '城市脉搏' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '打开今日村落日报' })).toHaveAttribute('href', '/capsules')
    expect(screen.getAllByRole('link', { name: '进入小镇' })[0]).toHaveAttribute('href', '/play')
    expect(screen.getByRole('link', { name: '查看我的居民' })).toHaveAttribute('href', '/profile')
    expect(eventNames()).toEqual(expect.arrayContaining([
      'living_loop_today_viewed',
      'living_loop_decision_viewed',
    ]))
  })

  it('previews a choice in an explicit confirmation region without submitting it', async () => {
    renderToday()
    const mediation = await screen.findByRole('radio', { name: /先组织一场私下调解/ })

    mediation.focus()
    expect(mediation).toHaveFocus()
    fireEvent.click(mediation)

    const confirmation = screen.getByRole('region', { name: '确认今天的选择' })
    expect(confirmation).toHaveTextContent('先组织一场私下调解')
    expect(confirmation).toHaveTextContent('先让双方在不公开升级冲突的情况下谈判。')
    expect(confirmation).toHaveTextContent('工人信任 +3')
    expect(livingLoopApi.chooseLivingLoopDecision).not.toHaveBeenCalled()
    expect(eventNames()).toContain('living_loop_choice_previewed')
  })

  it('submits a choice at most once even when confirmation is clicked repeatedly', async () => {
    let resolveChoice!: (decision: ReturnType<typeof chosenDecision>) => void
    livingLoopApi.chooseLivingLoopDecision.mockReturnValue(
      new Promise((resolve) => { resolveChoice = resolve }),
    )
    renderToday()
    fireEvent.click(await screen.findByRole('radio', { name: /先组织一场私下调解/ }))
    const confirm = screen.getByRole('button', { name: '确认这个选择' })

    fireEvent.click(confirm)
    fireEvent.click(confirm)

    expect(livingLoopApi.chooseLivingLoopDecision).toHaveBeenCalledTimes(1)
    expect(confirm).toBeDisabled()
    expect(livingLoopApi.chooseLivingLoopDecision).toHaveBeenCalledWith(
      DECISION_ID,
      expect.objectContaining({
        choice_key: 'private_mediation',
        idempotency_key: expect.any(String),
      }),
    )

    await act(async () => { resolveChoice(chosenDecision()) })
    expect(await screen.findByRole('heading', { name: '决定已经保存' })).toBeInTheDocument()
  })

  it('shows only the server-confirmed immediate result and waiting time, then moves focus', async () => {
    renderToday()
    fireEvent.click(await screen.findByRole('radio', { name: /先组织一场私下调解/ }))
    fireEvent.click(screen.getByRole('button', { name: '确认这个选择' }))

    const immediateHeading = await screen.findByRole('heading', { name: '决定已经保存' })
    expect(immediateHeading).toHaveFocus()
    expect(screen.getByText('工人信任 +3')).toBeInTheDocument()
    expect(screen.getByRole('timer', { name: '延迟后果可查看时间' })).toBeInTheDocument()
    expect(screen.queryByText(delayedResult.summary)).not.toBeInTheDocument()
    expect(eventNames()).toContain('living_loop_immediate_result_viewed')
  })

  it('restores a previously chosen decision from the aggregate response without resubmitting', async () => {
    livingLoopApi.getLivingLoopToday.mockResolvedValue(readyProjection(chosenDecision()))

    renderToday()

    expect(await screen.findByRole('heading', { name: '决定已经保存' })).toBeInTheDocument()
    expect(screen.getByRole('timer', { name: '延迟后果可查看时间' })).toBeInTheDocument()
    expect(screen.queryByText(delayedResult.summary)).not.toBeInTheDocument()
    expect(livingLoopApi.chooseLivingLoopDecision).not.toHaveBeenCalled()
  })

  it('refreshes from the server when the waiting countdown reaches zero instead of revealing locally', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-28T12:00:00Z'))
    livingLoopApi.getLivingLoopToday
      .mockResolvedValueOnce(readyProjection(chosenDecision('2026-08-28T12:00:01Z')))
      .mockResolvedValueOnce(readyProjection(readyDecision()))

    renderToday()
    await act(async () => { await Promise.resolve() })
    expect(livingLoopApi.getLivingLoopToday).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(delayedResult.summary)).not.toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000)
    })

    expect(livingLoopApi.getLivingLoopToday).toHaveBeenCalledTimes(2)
    expect(screen.getByText(delayedResult.summary)).toBeInTheDocument()
    expect(livingLoopApi.markLivingLoopResultViewed).toHaveBeenCalledTimes(1)
  })

  it('acknowledges a ready delayed result once, keeps it visible, and moves focus to it', async () => {
    livingLoopApi.getLivingLoopToday.mockResolvedValue(readyProjection(readyDecision()))

    renderToday()

    const delayedHeading = await screen.findByRole('heading', { name: '港口传来新进展' })
    expect(delayedHeading).toHaveFocus()
    expect(screen.getByText(delayedResult.summary)).toBeInTheDocument()
    await waitFor(() => expect(livingLoopApi.markLivingLoopResultViewed).toHaveBeenCalledTimes(1))
    expect(livingLoopApi.markLivingLoopResultViewed).toHaveBeenCalledWith(DECISION_ID)
    expect(eventNames()).toContain('living_loop_delayed_result_viewed')
  })

  it('keeps choice confirmation and navigation working when every telemetry request fails', async () => {
    livingLoopApi.postProductEventsBatch.mockRejectedValue(new Error('telemetry unavailable'))
    renderToday()
    fireEvent.click(await screen.findByRole('radio', { name: /先组织一场私下调解/ }))
    fireEvent.click(screen.getByRole('button', { name: '确认这个选择' }))

    expect(await screen.findByRole('heading', { name: '决定已经保存' })).toBeInTheDocument()
    expect(livingLoopApi.chooseLivingLoopDecision).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getAllByRole('link', { name: '进入小镇' })[0])
    expect(screen.getByTestId('today-location')).toHaveTextContent('/play')
  })

  it('renders backend text as text and preserves native control semantics', async () => {
    const unsafe = readyProjection({
      ...pendingDecision,
      context: '<img src="x" onerror="alert(1)">港口仍在等待处理。',
    })
    livingLoopApi.getLivingLoopToday.mockResolvedValue(unsafe)

    const view = renderToday()

    expect(await screen.findByText(/<img src="x"/)).toBeInTheDocument()
    expect(view.container.querySelector('img[src="x"]')).toBeNull()
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).toHaveAttribute('type', 'radio')
      expect(radio).not.toBeDisabled()
    }
  })
})
