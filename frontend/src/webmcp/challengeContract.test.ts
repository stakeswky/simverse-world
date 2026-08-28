import '@testing-library/jest-dom/vitest'

import { cleanup, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AgentActivityPanel } from '../components/challenge/AgentActivityPanel'
import type { ChallengeProjection } from '../services/api/challenge'
import {
  ChallengeWebMcpHarness,
  challengeProjection,
} from '../test/challengeWebMcpHarness'
import { resetAgentActivityForTests } from './activity'
import {
  COMMIT_TOOL_NAME,
  INVESTIGATE_TOOL_NAME,
  PREVIEW_TOOL_NAME,
  RESET_TOOL_NAME,
  VERIFY_TOOL_NAME,
  createChallengeTool,
  type ChallengeToolStore,
} from './challengeTools'
import {
  buildCommitToolOutput,
  buildInvestigateToolOutput,
  buildPreviewToolOutput,
  buildResetToolOutput,
  buildVerifyToolOutput,
} from './challengeToolResults'
import {
  CHALLENGE_TOOL_NAMES,
  ChallengeToolSurfaceManager,
  STALE_TOOL_SURFACE_RESULT,
} from './challengeToolSurfaceManager'
import type { WebMcpModelContext } from './types'

const HASH_A = `sha256:${'a'.repeat(64)}`
const HASH_B = `sha256:${'b'.repeat(64)}`
const HASH_C = `sha256:${'c'.repeat(64)}`

function toolStore(session: ChallengeProjection = challengeProjection()) {
  const actions = {
    investigate: vi.fn(async () => undefined),
    preview: vi.fn(async () => undefined),
    commit: vi.fn(async () => undefined),
    verify: vi.fn(async () => undefined),
    reset: vi.fn(async () => undefined),
  }
  const store: ChallengeToolStore = {
    getState: () => ({ session, ...actions }),
  }
  return { actions, store }
}

const contracts = [
  {
    name: INVESTIGATE_TOOL_NAME,
    title: 'Investigate Harbor crisis',
    description: 'Read cross-domain evidence for the isolated Harbor wage crisis without changing the world.',
    inputSchema: {
      type: 'object',
      properties: {
        budget_cap_sc: { type: 'integer', minimum: 1, maximum: 300 },
      },
      required: ['budget_cap_sc'],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, untrustedContentHint: true },
    validInput: { budget_cap_sc: 300 },
    action: 'investigate' as const,
  },
  {
    name: PREVIEW_TOOL_NAME,
    title: 'Preview Harbor intervention',
    description: 'Build an immutable World Diff and deterministic 72-hour forecast without changing the challenge world.',
    inputSchema: {
      type: 'object',
      properties: {
        crisis_id: { type: 'string', enum: ['harbor-wage-crisis'] },
        budget_cap_sc: { type: 'integer', const: 300 },
      },
      required: ['crisis_id', 'budget_cap_sc'],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
    validInput: { crisis_id: 'harbor-wage-crisis', budget_cap_sc: 300 },
    action: 'preview' as const,
  },
  {
    name: COMMIT_TOOL_NAME,
    title: 'Commit approved Harbor intervention',
    description: 'Use the one-time capability for the exact approved diff. This action is irreversible inside the disposable Challenge Town.',
    inputSchema: {
      type: 'object',
      properties: {
        preview_id: { type: 'string' },
        expected_world_version: { type: 'integer' },
        diff_hash: { type: 'string', pattern: '^sha256:[0-9a-f]{64}$' },
      },
      required: ['preview_id', 'expected_world_version', 'diff_hash'],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
    validInput: {
      preview_id: 'preview-01',
      expected_world_version: 7,
      diff_hash: HASH_B,
    },
    action: 'commit' as const,
  },
  {
    name: VERIFY_TOOL_NAME,
    title: 'Verify 72-hour Harbor outcome',
    description: 'Advance the committed isolated Challenge Town by exactly 72 hours and compare its actual result with the forecast and paired no-action control.',
    inputSchema: {
      type: 'object',
      properties: {
        receipt_id: { type: 'string' },
        advance_hours: { type: 'integer', const: 72 },
      },
      required: ['receipt_id', 'advance_hours'],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
    validInput: { receipt_id: 'SV-2042-A1B2C3D4', advance_hours: 72 },
    action: 'verify' as const,
  },
  {
    name: RESET_TOOL_NAME,
    title: 'Reset isolated Challenge Town',
    description: 'Discard the terminal challenge run and restore a new anonymous session at the locked public v7 fixture.',
    inputSchema: {
      type: 'object',
      properties: { expected_generation: { type: 'string' } },
      required: ['expected_generation'],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
    validInput: { expected_generation: 'generation-01' },
    action: 'reset' as const,
  },
] as const

function compactOutputProjections(): ChallengeProjection[] {
  const investigated = challengeProjection({
    state: 'EVIDENCE_READY',
    tool_surface: [INVESTIGATE_TOOL_NAME, PREVIEW_TOOL_NAME],
    evidence: {
      evidence_id: 'evidence-01',
      based_on_world_version: 7,
      crisis_id: 'harbor-wage-crisis',
      priority_score: 94,
      region_id: 'harbor',
      affected_resident_ids: ['harbor-resident-01'],
      evidence: [{
        evidence_type: 'economic',
        source_id: 'ledger',
        title: 'Ledger',
        detail: '180 SC overdue',
        untrusted: false,
      }],
      enforced_constraints: ['budget_lte_300_sc'],
    },
  })
  const previewed = challengeProjection({
    state: 'PREVIEW_READY',
    tool_surface: [PREVIEW_TOOL_NAME],
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
        resident_cash_changes: [],
        food_credit_changes: [],
        employer_claims_created: [],
        events_created: [],
        explicitly_unchanged: ['production_town_state'],
      },
      diff_hash: HASH_B,
      forecast: {
        seeds: [101, 102, 103, 104, 105],
        high_food_risk_residents: { min: 0, max: 1 },
        social_tension: { min: 50, max: 58 },
        strike_risk_pct: { min: 28, max: 42 },
        stabilized_residents: { min: 5, max: 6 },
      },
      rejected_alternatives: [],
      created_at: '2042-06-12T08:05:00Z',
    },
  })
  const receipt = {
    receipt_id: 'SV-2042-A1B2C3D4',
    scenario_id: 'harbor-wage-crisis-v1' as const,
    session_generation: 'generation-01',
    preview_id: 'preview-01',
    approval_fingerprint: 'appr-A1B2',
    approved_diff_hash: HASH_B,
    world_before_version: 7,
    world_after_version: 8,
    world_before_hash: HASH_A,
    world_after_hash: HASH_C,
    budget_before_sc: 300,
    budget_delta_sc: -240,
    budget_after_sc: 60,
    affected_residents: ['harbor-resident-01'],
    created_events: ['employer-escrow-mediation'],
    verified_invariants: ['challenge_town_isolated'],
  }
  const committed = challengeProjection({
    ...previewed,
    state: 'COMMITTED',
    world_version: 8,
    world_hash: HASH_C,
    budget_sc: 60,
    tool_surface: [VERIFY_TOOL_NAME],
    receipt,
  })
  const baselineMetrics = {
    high_food_risk_residents: 2,
    social_tension: 68,
    strike_risk_pct: 74,
    stabilized_residents: 0,
  }
  const verified = challengeProjection({
    ...committed,
    state: 'VERIFIED',
    world_version: 9,
    world_time: '2042-06-15T08:00:00Z',
    tool_surface: [RESET_TOOL_NAME],
    verification: {
      receipt_id: receipt.receipt_id,
      advance_hours: 72,
      baseline_snapshot: {
        tick_index: 0,
        elapsed_hours: 0,
        world_time: '2042-06-12T08:00:00Z',
        metrics: baselineMetrics,
        external_event_ids: [],
      },
      tick_snapshots: Array.from({ length: 12 }, (_, index) => ({
        tick_index: index + 1,
        elapsed_hours: (index + 1) * 6,
        world_time: new Date(
          Date.parse('2042-06-12T08:00:00Z') + (index + 1) * 21_600_000,
        ).toISOString(),
        metrics: baselineMetrics,
        external_event_ids: [`harbor-market-shift-${index + 1}`],
      })),
      forecast: previewed.preview!.forecast,
      actual: {
        high_food_risk_residents: 1,
        social_tension: 54,
        strike_risk_pct: 38,
        stabilized_residents: 5,
      },
      no_action: {
        high_food_risk_residents: 3,
        social_tension: 81,
        strike_risk_pct: 100,
        stabilized_residents: 0,
        strike_event_triggered: true,
      },
      notable_deviation: 'Escrow miss caused a notable deviation.',
    },
  })
  const reset = challengeProjection({
    session_generation: 'generation-02',
    world_hash: HASH_A,
  })
  return [investigated, previewed, committed, verified, reset]
}

afterEach(() => {
  cleanup()
  resetAgentActivityForTests()
  vi.restoreAllMocks()
})

describe('final five-tool WebMCP contract', () => {
  it('locks exact catalogue, descriptions, schemas, annotations, and compact inputs', () => {
    const { store } = toolStore()
    expect(CHALLENGE_TOOL_NAMES).toEqual(contracts.map(({ name }) => name))
    expect(CHALLENGE_TOOL_NAMES).not.toContain('simverse_get_challenge_status')

    for (const expected of contracts) {
      const definition = createChallengeTool(expected.name, { store, document })
      expect(definition).toMatchObject({
        name: expected.name,
        title: expected.title,
        description: expected.description,
        inputSchema: expected.inputSchema,
        annotations: expected.annotations,
      })
      expect(definition.description.length).toBeGreaterThan(20)
      expect(definition.description.length).toBeLessThanOrEqual(180)
      expect(JSON.stringify(definition.inputSchema).length).toBeLessThan(512)
    }
  })

  it('keeps all success summaries under 1500 characters and free of secrets', () => {
    const [investigated, previewed, committed, verified, reset] = compactOutputProjections()
    const outputs = [
      buildInvestigateToolOutput(investigated),
      buildPreviewToolOutput(previewed),
      buildCommitToolOutput(committed),
      buildVerifyToolOutput(verified),
      buildResetToolOutput(reset),
    ]
    expect(outputs).toHaveLength(5)
    for (const output of outputs) {
      const serialized = JSON.stringify(output)
      expect(serialized.length).toBeLessThan(1500)
      expect(serialized).not.toMatch(
        /csrf|cookie|jwt|authorization|bearer|initial_world_hash|approval_id|redis|internal\/server|stack/i,
      )
    }
  })

  it('returns fixed safe errors for invalid and pre-aborted inputs', async () => {
    const { actions, store } = toolStore()
    for (const contract of contracts) {
      const definition = createChallengeTool(contract.name, { store, document })
      const invalid = await definition.execute(
        { ...contract.validInput, input_secret: 'must-not-echo' },
        { signal: new AbortController().signal },
      )
      expect(invalid).toMatchObject({
        error: { code: 'INVALID_INPUT', retryable: false },
      })
      expect(JSON.stringify(invalid)).not.toContain('must-not-echo')

      const controller = new AbortController()
      controller.abort()
      const aborted = await definition.execute(
        contract.validInput,
        { signal: controller.signal },
      )
      expect(aborted).toMatchObject({
        error: { code: 'REQUEST_ABORTED', retryable: true },
      })
      expect(actions[contract.action]).not.toHaveBeenCalled()
    }
  })

  it('executes every tool when the browser omits execution options', async () => {
    for (const contract of contracts) {
      const { actions, store } = toolStore()
      const definition = createChallengeTool(contract.name, { store, document })

      await expect(definition.execute(contract.validInput)).resolves.toBeDefined()
      expect(actions[contract.action]).toHaveBeenCalledOnce()
    }
  })

  it('updates the visible Agent Activity region after an actual tool execution', async () => {
    const { store } = toolStore()
    render(createElement(AgentActivityPanel, { toolDocument: document }))
    expect(screen.getByText('No tool calls yet')).toBeInTheDocument()

    await createChallengeTool(INVESTIGATE_TOOL_NAME, { store, document }).execute(
      { budget_cap_sc: 300, input_secret: 'must-not-render' },
      { signal: new AbortController().signal },
    )

    expect(await screen.findByText(INVESTIGATE_TOOL_NAME)).toBeInTheDocument()
    expect(screen.getByText('investigate · failed')).toBeInTheDocument()
    expect(screen.getByText('INVALID_INPUT')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('must-not-render')
  })

  it('registers only the state surface, stales old handlers, and unregisters on route exit', async () => {
    const harness = new ChallengeWebMcpHarness()
    const { store } = toolStore()
    const manager = new ChallengeToolSurfaceManager({
      modelContext: harness.modelContext,
      createTool: (name) => createChallengeTool(name, { store, document }),
      reload: harness.reload,
    })
    const states: ChallengeProjection[] = [
      challengeProjection(),
      challengeProjection({
        state: 'EVIDENCE_READY',
        tool_surface: [INVESTIGATE_TOOL_NAME, PREVIEW_TOOL_NAME],
      }),
      challengeProjection({ state: 'PREVIEW_READY', tool_surface: [PREVIEW_TOOL_NAME] }),
      challengeProjection({ state: 'APPROVED_ONCE', tool_surface: [COMMIT_TOOL_NAME] }),
      challengeProjection({ state: 'COMMITTED', world_version: 8, tool_surface: [VERIFY_TOOL_NAME] }),
      challengeProjection({ state: 'VERIFIED', world_version: 9, tool_surface: [RESET_TOOL_NAME] }),
      challengeProjection({ state: 'FAILED', world_version: 8, tool_surface: [RESET_TOOL_NAME] }),
      challengeProjection({ state: 'EXPIRED', tool_surface: [RESET_TOOL_NAME] }),
      challengeProjection({ session_generation: 'generation-02' }),
    ]

    let oldTool: ReturnType<ChallengeWebMcpHarness['tool']>
    for (const state of states) {
      await expect(manager.sync(state)).resolves.toBe('registered')
      if (oldTool) {
        expect(await oldTool.execute(
          {},
          { signal: new AbortController().signal },
        )).toEqual(STALE_TOOL_SURFACE_RESULT)
      }
      expect(harness.toolNames()).toEqual([...state.tool_surface].sort())
      oldTool = harness.tool(state.tool_surface[0]!)
    }

    manager.destroy()
    expect(harness.toolNames()).toEqual([])
  })

  it('does not install an old registration that resolves after a newer epoch', async () => {
    let resolveOld: () => void = () => undefined
    const oldRegistration = new Promise<void>((resolve) => {
      resolveOld = resolve
    })
    const harness = new ChallengeWebMcpHarness()
    harness.queueRegistrationOutcome(oldRegistration)
    const { store } = toolStore()
    const manager = new ChallengeToolSurfaceManager({
      modelContext: harness.modelContext,
      createTool: (name) => createChallengeTool(name, { store, document }),
      reload: harness.reload,
    })

    const oldState = manager.sync(challengeProjection())
    await Promise.resolve()
    const newState = manager.sync(challengeProjection({
      state: 'PREVIEW_READY',
      tool_surface: [PREVIEW_TOOL_NAME],
    }))
    await expect(newState).resolves.toBe('registered')
    resolveOld()

    await expect(oldState).resolves.toBe('stale')
    expect(harness.registrationCalls[0]?.options?.signal?.aborted).toBe(true)
    expect(harness.toolNames()).toEqual([PREVIEW_TOOL_NAME])
  })

  it('fails open to the ordinary UI when WebMCP is disabled or unsupported', async () => {
    const createTool = vi.fn(() => createChallengeTool(INVESTIGATE_TOOL_NAME))
    const disabled = new ChallengeToolSurfaceManager({ enabled: false, createTool })
    await expect(disabled.sync(challengeProjection())).resolves.toBe('disabled')
    expect(createTool).not.toHaveBeenCalled()

    const unsupported = new ChallengeToolSurfaceManager({
      modelContext: new EventTarget() as WebMcpModelContext,
      createTool,
    })
    await expect(unsupported.sync(challengeProjection())).resolves.toBe('unsupported')
    expect(createTool).not.toHaveBeenCalled()
  })

  it('documents only the final surface and quarantines the Day-0 probe to diagnostics', () => {
    const documentPath = resolve(
      process.cwd(),
      '../docs/webmcp-challenge/WEBMCP_TOOLS.md',
    )
    const contractDocument = readFileSync(documentPath, 'utf8')
    for (const { name } of contracts) expect(contractDocument).toContain(name)
    expect(contractDocument).toContain('diagnostics=1')
    expect(contractDocument).toContain('AbortSignal')
    expect(contractDocument).not.toMatch(
      /`inspect_town_signals`|`focus_evidence`|`draft_interventions`|`commit_intervention`/,
    )
  })
})
