import '@testing-library/jest-dom/vitest'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChallengeProjection } from '../services/api/challenge'
import { ChallengeWebMcpHarness } from '../test/challengeWebMcpHarness'
import { resetAgentActivityForTests } from '../webmcp/activity'
import { resetWebMcpRegistrationsForTests } from '../webmcp/registerChallengeStatusTool'
import type { WebMcpToolDefinition } from '../webmcp/types'

const store = vi.hoisted(() => ({
  session: null as ChallengeProjection | null,
  loading: false,
  activeToolNames: [] as readonly string[],
  registrationState: 'unsupported' as const,
  error: null as Error | null,
  initialize: vi.fn<() => Promise<void>>(),
  investigate: vi.fn(),
  preview: vi.fn(),
  approve: vi.fn(),
  revoke: vi.fn(),
  reset: vi.fn(),
  setRegistrationState: vi.fn(),
}))

vi.mock('../stores/challengeStore', () => ({
  useChallengeStore: (selector: (state: typeof store) => unknown) => selector(store),
}))

import { ChallengePage } from './ChallengePage'

function projection(overrides: Partial<ChallengeProjection> = {}): ChallengeProjection {
  const residents = Array.from({ length: 6 }, (_, index) => ({
    resident_id: `harbor-resident-${String(index + 1).padStart(2, '0')}`,
    name: `Harbor Resident ${String(index + 1).padStart(2, '0')}`,
    cash_sc: 10,
    unpaid_wage_sc: 30,
    food_risk: index < 2 ? 'HIGH' as const : 'MEDIUM' as const,
    food_credit_sc: 0,
    stabilized: false,
  }))
  return {
    session_generation: 'generation-01',
    state: 'INITIAL',
    scenario_id: 'harbor-wage-crisis-v1',
    fixture_version: 1,
    world_version: 7,
    world_hash: `sha256:${'a'.repeat(64)}`,
    world_time: '2042-06-12T08:00:00Z',
    budget_sc: 300,
    tool_surface: ['simverse_investigate_crisis'],
    expires_at: '2042-06-12T08:15:00Z',
    csrf_token: 'csrf-01',
    world: {
      scenario_id: 'harbor-wage-crisis-v1',
      fixture_version: 1,
      world_version: 7,
      world_time: '2042-06-12T08:00:00Z',
      budget_sc: 300,
      harbor_open: true,
      residents,
      employers: [
        { employer_id: 'harbor-employer-a', name: 'Harbor Freight Cooperative', overdue_payroll_sc: 90, repayment_claim_sc: 0, escrow_status: 'NONE' },
        { employer_id: 'harbor-employer-b', name: 'North Pier Logistics', overdue_payroll_sc: 90, repayment_claim_sc: 0, escrow_status: 'NONE' },
      ],
      relationships: [],
      events: [],
      metrics: {
        unpaid_residents: 6,
        high_food_risk_residents: 2,
        social_tension: 68,
        strike_risk_pct: 74,
        stabilized_residents: 0,
      },
    },
    evidence: null,
    preview: null,
    approval_fingerprint: null,
    approval_expires_at: null,
    receipt: null,
    verification: null,
    ...overrides,
  }
}

function previewProjection(
  overrides: Partial<ChallengeProjection> = {},
): ChallengeProjection {
  const base = projection()
  return projection({
    state: 'PREVIEW_READY',
    tool_surface: ['simverse_preview_intervention'],
    evidence: {
      evidence_id: 'evidence-01',
      based_on_world_version: 7,
      crisis_id: 'harbor-wage-crisis',
      priority_score: 94,
      region_id: 'harbor',
      affected_resident_ids: base.world.residents.map(
        (resident) => resident.resident_id,
      ),
      evidence: [],
      enforced_constraints: ['budget_lte_300_sc'],
    },
    preview: {
      preview_id: 'preview-01',
      crisis_id: 'harbor-wage-crisis',
      based_on_world_version: 7,
      intervention_id: 'harbor-wage-bridge',
      total_cost_sc: 240,
      remaining_budget_sc: 60,
      diff: {
        scenario_id: 'harbor-wage-crisis-v1',
        session_generation: 'generation-01',
        preview_id: 'preview-01',
        based_on_world_version: 7,
        budget_before_sc: 300,
        budget_after_sc: 60,
        resident_cash_changes: base.world.residents.map((resident) => ({
          resident_id: resident.resident_id,
          before_sc: 10,
          delta_sc: 30,
          after_sc: 40,
        })),
        food_credit_changes: base.world.residents.slice(0, 2).map((resident) => ({
          resident_id: resident.resident_id,
          before_sc: 0,
          delta_sc: 20,
          after_sc: 20,
        })),
        employer_claims_created: base.world.employers.map((employer) => ({
          employer_id: employer.employer_id,
          amount_sc: 90,
          status: 'PENDING' as const,
        })),
        events_created: [{
          event_id: 'employer-escrow-mediation',
          event_type: 'MEDIATION',
          region_id: 'harbor-district',
          title: 'Employer escrow mediation opened',
          description: 'Harbor employers enter mediation.',
          occurs_at: '2042-06-12T08:05:00Z',
        }],
        explicitly_unchanged: [
          'resident_personality',
          'resident_preferences',
          'resident_intentions',
          'direct_relationship_scores',
          'harbor_operating_status',
          'production_town_state',
        ],
      },
      diff_hash: `sha256:${'b'.repeat(64)}`,
      forecast: {
        seeds: [101, 102, 103, 104, 105],
        high_food_risk_residents: { min: 0, max: 1 },
        social_tension: { min: 50, max: 58 },
        strike_risk_pct: { min: 28, max: 42 },
        stabilized_residents: { min: 5, max: 6 },
      },
      rejected_alternatives: [
        {
          alternative_id: 'universal-town-subsidy',
          title: 'Universal town subsidy',
          total_cost_sc: 320,
          rejected_reason: 'BUDGET_EXCEEDED',
          violated_invariants: ['budget_lte_300_sc'],
        },
        {
          alternative_id: 'forced-rewrite-and-harbor-closure',
          title: 'Forced morale rewrite and Harbor closure',
          total_cost_sc: null,
          rejected_reason: 'POLICY_VIOLATION',
          violated_invariants: [
            'harbor_must_remain_open',
            'no_direct_preference_rewrite',
            'no_direct_relationship_rewrite',
          ],
        },
      ],
      created_at: '2042-06-12T08:05:00Z',
    },
    ...overrides,
  })
}

function renderPage(path = '/challenge') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ChallengePage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  store.session = projection()
  store.loading = false
  store.activeToolNames = ['simverse_investigate_crisis']
  store.registrationState = 'unsupported'
  store.error = null
  store.initialize.mockReset().mockResolvedValue(undefined)
  store.investigate.mockReset().mockResolvedValue({
    structuredContent: { state: 'EVIDENCE_READY' },
  })
  store.preview.mockReset().mockResolvedValue({
    structuredContent: { state: 'PREVIEW_READY' },
  })
  store.approve.mockReset().mockResolvedValue(undefined)
  store.revoke.mockReset().mockResolvedValue(undefined)
  store.reset.mockReset().mockResolvedValue({ structuredContent: { state: 'INITIAL' } })
  store.setRegistrationState.mockReset()
  vi.stubEnv('VITE_WEBMCP_ENABLED', 'true')
})

afterEach(() => {
  cleanup()
  resetWebMcpRegistrationsForTests()
  resetAgentActivityForTests()
  vi.unstubAllEnvs()
  vi.useRealTimers()
  Reflect.deleteProperty(document, 'modelContext')
  Reflect.deleteProperty(navigator, 'modelContext')
})

describe('ChallengePage', () => {
  it('initializes once and renders the server projection header', async () => {
    renderPage()

    await waitFor(() => expect(store.initialize).toHaveBeenCalledTimes(1))
    expect(screen.getByText('harbor-wage-crisis-v1')).toBeInTheDocument()
    expect(screen.getAllByText('INITIAL').length).toBeGreaterThan(0)
    expect(screen.getAllByText('World v7').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/2042-06-12/).length).toBeGreaterThan(0)
    expect(screen.getByText('Budget 300 SC')).toBeInTheDocument()
    expect(screen.getByText('1 active tool')).toBeInTheDocument()
    expect(screen.getByText('simverse_investigate_crisis')).toBeInTheDocument()
    expect(screen.getByText('Site Tools unavailable')).toBeInTheDocument()
    expect(screen.getByText(/Expires/)).toBeInTheDocument()
  })

  it('renders the isolated Harbor map, fixture entities, and five key metrics', () => {
    renderPage()

    expect(screen.getByRole('img', { name: 'Harbor district challenge map' })).toBeInTheDocument()
    expect(screen.getByText('6 residents')).toBeInTheDocument()
    expect(screen.getByText('2 employers')).toBeInTheDocument()
    expect(screen.getByText('Unpaid residents')).toBeInTheDocument()
    expect(screen.getByText('High food risk')).toBeInTheDocument()
    expect(screen.getByText('Social tension')).toBeInTheDocument()
    expect(screen.getByText('Strike risk')).toBeInTheDocument()
    expect(screen.getByText('Stabilized')).toBeInTheDocument()
    expect(screen.getByTestId('metric-unpaid')).toHaveTextContent('6')
    expect(screen.getByTestId('metric-high-risk')).toHaveTextContent('2')
    expect(screen.getByTestId('metric-tension')).toHaveTextContent('68')
    expect(screen.getByTestId('metric-strike')).toHaveTextContent('74%')
    expect(screen.getByTestId('metric-stabilized')).toHaveTextContent('0')
  })

  it('focuses Harbor and highlights all six affected residents after investigation', () => {
    const base = projection()
    store.session = projection({
      state: 'EVIDENCE_READY',
      evidence: {
        evidence_id: 'evidence-01',
        based_on_world_version: 7,
        crisis_id: 'harbor-wage-crisis',
        priority_score: 94,
        region_id: 'harbor',
        affected_resident_ids: base.world.residents.map((resident) => resident.resident_id),
        evidence: [],
        enforced_constraints: ['budget_lte_300_sc'],
      },
    })
    renderPage()

    expect(screen.getByTestId('harbor-map')).toHaveAttribute('data-focused', 'true')
    expect(screen.getAllByTestId('affected-resident')).toHaveLength(6)
    expect(screen.getByText('Harbor focus active')).toBeInTheDocument()
    expect(screen.getByText('Evidence snapshot')).toBeInTheDocument()
    expect(screen.getByText('Priority 94')).toBeInTheDocument()
  })

  it('uses the same investigate store action from the visible ordinary-browser control', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Investigate Harbor crisis' }))

    await waitFor(() => expect(store.investigate).toHaveBeenCalledTimes(1))
    expect(store.investigate).toHaveBeenCalledWith({ budget_cap_sc: 300 })
  })

  it('renders guaranteed changes separately from the deterministic 72h forecast', () => {
    store.session = previewProjection()
    store.activeToolNames = ['simverse_preview_intervention']
    renderPage()

    const guaranteed = screen.getByRole('heading', {
      name: 'Guaranteed on commit',
    }).closest('section')
    const forecast = screen.getByRole('heading', {
      name: 'Forecast over 72h',
    }).closest('section')
    expect(guaranteed).not.toBeNull()
    expect(forecast).not.toBeNull()
    expect(within(guaranteed!).getByText('6 wage transfers')).toBeInTheDocument()
    expect(within(guaranteed!).getByText('2 food credits')).toBeInTheDocument()
    expect(within(guaranteed!).getByText('2 employer claims')).toBeInTheDocument()
    expect(within(guaranteed!).getByText('1 mediation event')).toBeInTheDocument()
    expect(within(guaranteed!).getByText('240 SC total')).toBeInTheDocument()
    expect(within(guaranteed!).getByText('60 SC remaining')).toBeInTheDocument()
    expect(within(guaranteed!).queryByText('50–58')).not.toBeInTheDocument()
    expect(within(forecast!).getByText('0–1')).toBeInTheDocument()
    expect(within(forecast!).getByText('50–58')).toBeInTheDocument()
    expect(within(forecast!).getByText('28–42%')).toBeInTheDocument()
    expect(within(forecast!).getByText('5–6')).toBeInTheDocument()
    expect(screen.getByText('Universal town subsidy')).toBeInTheDocument()
    expect(screen.getByText('BUDGET_EXCEEDED')).toBeInTheDocument()
    expect(screen.getByText('Forced morale rewrite and Harbor closure')).toBeInTheDocument()
    expect(screen.getByText('POLICY_VIOLATION')).toBeInTheDocument()
    expect(screen.getAllByTestId('unchanged-invariant')).toHaveLength(6)
    expect(screen.getByText('World v7 · sha256:bbbbbbbbbbbb…')).toBeInTheDocument()
    expect(screen.getByText('Review required')).toBeInTheDocument()
    expect(screen.getByText(/deterministic isolated simulation/i)).toBeInTheDocument()
  })

  it('renders the visible approval gate and rejects a programmatic DOM click', () => {
    store.session = previewProjection()
    store.activeToolNames = ['simverse_preview_intervention']
    renderPage()

    expect(screen.getByText(
      'Commit capability is not available to the agent.',
    )).toBeInTheDocument()
    const approve = screen.getByRole('button', {
      name: 'Create one-time approval',
    })
    expect(approve).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', {
      name: 'I reviewed this exact World Diff.',
    }))
    expect(approve).toBeEnabled()
    approve.click()
    expect(store.approve).not.toHaveBeenCalled()
    expect(document.body.innerHTML).not.toContain('csrf-01')
    expect(document.body.innerHTML).not.toContain('sv_challenge_approval')
  })

  it('shows and revokes the safe one-time approval fingerprint', async () => {
    store.session = previewProjection({
      state: 'APPROVED_ONCE',
      tool_surface: ['simverse_commit_approved'],
      approval_fingerprint: 'appr-A1B2',
      approval_expires_at: '2042-06-12T08:06:30Z',
    })
    store.activeToolNames = ['simverse_commit_approved']
    renderPage()

    expect(screen.getByText('appr-A1B2')).toBeInTheDocument()
    expect(screen.getByText('2042-06-12T08:06:30Z')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Revoke approval' }))
    await waitFor(() => expect(store.revoke).toHaveBeenCalledTimes(1))
  })

  it('refreshes the session at approval expiry and removes the commit tool', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2042-06-12T08:05:00Z'))
    const harness = new ChallengeWebMcpHarness()
    Object.defineProperty(navigator, 'modelContext', {
      configurable: true,
      value: harness.modelContext,
    })
    store.session = previewProjection({
      state: 'APPROVED_ONCE',
      tool_surface: ['simverse_commit_approved'],
      approval_fingerprint: 'appr-A1B2',
      approval_expires_at: '2042-06-12T08:06:30Z',
    })
    store.activeToolNames = ['simverse_commit_approved']
    store.initialize.mockImplementation(async () => {
      if (store.initialize.mock.calls.length === 2) {
        store.session = previewProjection()
        store.activeToolNames = ['simverse_preview_intervention']
      }
    })
    const page = renderPage()
    await vi.advanceTimersByTimeAsync(0)
    expect(store.initialize).toHaveBeenCalledTimes(1)
    expect(harness.toolNames()).toEqual(['simverse_commit_approved'])

    await vi.advanceTimersByTimeAsync(90_000)
    expect(store.initialize).toHaveBeenCalledTimes(2)
    page.rerender(
      <MemoryRouter initialEntries={['/challenge']}>
        <ChallengePage />
      </MemoryRouter>,
    )
    await vi.advanceTimersByTimeAsync(0)

    expect(harness.toolNames()).toEqual(['simverse_preview_intervention'])
    expect(harness.toolNames()).not.toContain('simverse_commit_approved')
  })

  it('renders the complete execution receipt and only the verify surface', () => {
    const approved = previewProjection()
    store.session = previewProjection({
      state: 'COMMITTED',
      world_version: 8,
      world_hash: `sha256:${'c'.repeat(64)}`,
      budget_sc: 60,
      tool_surface: ['simverse_verify_outcome'],
      approval_fingerprint: null,
      approval_expires_at: null,
      receipt: {
        receipt_id: 'SV-2042-A1B2C3D4',
        scenario_id: 'harbor-wage-crisis-v1',
        session_generation: approved.session_generation,
        preview_id: approved.preview!.preview_id,
        approval_fingerprint: 'appr-A1B2',
        approved_diff_hash: approved.preview!.diff_hash,
        world_before_version: 7,
        world_after_version: 8,
        world_before_hash: `sha256:${'a'.repeat(64)}`,
        world_after_hash: `sha256:${'c'.repeat(64)}`,
        budget_before_sc: 300,
        budget_delta_sc: -240,
        budget_after_sc: 60,
        affected_residents: approved.world.residents.map(
          (resident) => resident.resident_id,
        ),
        created_events: ['employer-escrow-mediation'],
        verified_invariants: [
          'budget_lte_300_sc',
          'challenge_town_isolated',
          'harbor_must_remain_open',
          'no_direct_preference_rewrite',
          'no_direct_relationship_rewrite',
        ],
      },
    })
    store.activeToolNames = ['simverse_verify_outcome']
    renderPage()

    const receipt = screen.getByRole('region', { name: 'Execution Receipt' })
    expect(within(receipt).getByText('SV-2042-A1B2C3D4')).toBeInTheDocument()
    expect(within(receipt).getByText('appr-A1B2')).toBeInTheDocument()
    expect(within(receipt).getByText('World v7 → v8')).toBeInTheDocument()
    expect(within(receipt).getByText('Budget 300 − 240 → 60 SC')).toBeInTheDocument()
    expect(within(receipt).getByText(`sha256:${'a'.repeat(64)}`)).toBeInTheDocument()
    expect(within(receipt).getByText(`sha256:${'c'.repeat(64)}`)).toBeInTheDocument()
    expect(within(receipt).getAllByTestId('receipt-resident')).toHaveLength(6)
    expect(within(receipt).getByText('employer-escrow-mediation')).toBeInTheDocument()
    expect(within(receipt).getAllByTestId('receipt-invariant')).toHaveLength(5)
    expect(screen.getByText('simverse_verify_outcome')).toBeInTheDocument()
    expect(screen.queryByRole('button', {
      name: 'Create one-time approval',
    })).not.toBeInTheDocument()
    expect(document.body.innerHTML).not.toContain('csrf-01')
    expect(document.body.innerHTML).not.toContain('sv_challenge_approval')
  })

  it('rebuilds through the store and clears stale approval presentation', async () => {
    store.session = previewProjection({
      state: 'APPROVED_ONCE',
      approval_fingerprint: 'fingerprint-old',
    })
    const firstRender = renderPage()
    expect(screen.getByText('Approved once')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', {
      name: 'Rebuild intervention preview',
    }))
    await waitFor(() => expect(store.preview).toHaveBeenCalledWith({
      crisis_id: 'harbor-wage-crisis',
      budget_cap_sc: 300,
    }))

    firstRender.unmount()
    store.session = previewProjection({ approval_fingerprint: null })
    renderPage()
    expect(screen.getByText('Review required')).toBeInTheDocument()
    expect(screen.queryByText('Approved once')).not.toBeInTheDocument()
  })

  it('shows a safe retry control after API failure', () => {
    store.session = null
    store.error = new Error('internal secret must not render')
    renderPage()

    expect(screen.getByRole('alert')).toHaveTextContent('Challenge session is temporarily unavailable.')
    expect(screen.queryByText('internal secret must not render')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry session' }))
    expect(store.initialize).toHaveBeenCalledTimes(2)
  })

  it('works without modelContext and can reset the in-memory session', async () => {
    store.session = projection({
      state: 'VERIFIED',
      tool_surface: ['simverse_reset_town'],
    })
    store.activeToolNames = ['simverse_reset_town']
    renderPage()

    expect(screen.getByText('Site Tools unavailable')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reset town' }))
    await waitFor(() => expect(store.reset).toHaveBeenCalledWith({
      expected_generation: 'generation-01',
    }))
  })

  it('registers the dynamic investigate tool without loading the Day-0 tool', async () => {
    const registerTool = vi.fn()
    const modelContext = Object.assign(new EventTarget(), { registerTool })
    Object.defineProperty(navigator, 'modelContext', {
      configurable: true,
      value: modelContext,
    })
    renderPage()

    await waitFor(() => expect(registerTool).toHaveBeenCalledTimes(1))
    expect(registerTool.mock.calls[0]?.[0]).toMatchObject({
      name: 'simverse_investigate_crisis',
    })
    expect(screen.queryByText('0.1.0')).not.toBeInTheDocument()
    expect(screen.queryByText('simverse_get_challenge_status')).not.toBeInTheDocument()
  })

  it('loads the legacy status tool only for diagnostics=1', async () => {
    let registeredTool: WebMcpToolDefinition | undefined
    const registerTool = vi.fn((tool: WebMcpToolDefinition) => {
      if (tool.name === 'simverse_get_challenge_status') registeredTool = tool
    })
    const modelContext = Object.assign(new EventTarget(), { registerTool })
    Object.defineProperty(navigator, 'modelContext', {
      configurable: true,
      value: modelContext,
    })
    renderPage('/challenge?diagnostics=1')

    await waitFor(() => expect(registeredTool?.name).toBe('simverse_get_challenge_status'))
    expect(screen.getByText('0.1.0')).toBeInTheDocument()
    expect(screen.getByText(registeredTool?.name ?? '')).toBeInTheDocument()
  })

  it('uses full-document links when leaving the isolated surface', () => {
    renderPage()
    expect(screen.getByRole('link', { name: 'Live town' })).toHaveAttribute('href', '/town')
    expect(screen.getByRole('link', { name: 'Enter world' })).toHaveAttribute('href', '/login')
  })
})
