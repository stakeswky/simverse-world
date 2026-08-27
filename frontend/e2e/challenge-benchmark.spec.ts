import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { renameSync, writeFileSync } from 'node:fs'

const API_BASE = 'http://localhost:8000'
const RAW_PATH = '/tmp/simverse-option-b-benchmark-raw.json'
const INVESTIGATE = 'simverse_investigate_crisis'
const PREVIEW = 'simverse_preview_intervention'
const COMMIT = 'simverse_commit_approved'
const VERIFY = 'simverse_verify_outcome'
const REQUIRED_EVENTS = [
  'task_started',
  'panel_opened',
  'crisis_identified',
  'preview_requested',
  'preview_ready',
  'approval_viewed',
  'approval_granted',
  'commit_attempted',
  'commit_succeeded',
  'verification_started',
  'verification_ready',
  'task_completed',
] as const

type BenchmarkMode = 'ordinary' | 'webmcp'

interface Projection {
  session_generation: string
  state: string
  world_version: number
  world_hash: string
  budget_sc: number
  csrf_token: string
  tool_surface: string[]
  preview: null | {
    preview_id: string
    based_on_world_version: number
    diff_hash: string
  }
  receipt: null | {
    receipt_id: string
    world_before_version: number
    world_after_version: number
    budget_before_sc: number
    budget_delta_sc: number
    budget_after_sc: number
  }
  verification: null | {
    receipt_id: string
    tick_snapshots: unknown[]
  }
}

interface ToolResult {
  state?: string
  preview_id?: string
  receipt_id?: string
  error?: { code?: string }
}

interface TelemetryEventRecord {
  event: string
  elapsed_ms: number
  fields: Record<string, unknown>
}

interface TelemetryRow {
  run_id: string
  mode: BenchmarkMode
  duration_ms: number
  clicks: number
  panel_switches: number
  route_switches: number
  wrong_selections: number
  success: boolean
  core_tool_calls: number
  unauthorized_attempts: number
  unauthorized_successes: number
  preview_rebuild_count: number
  events: TelemetryEventRecord[]
}

interface BenchmarkRow extends TelemetryRow {
  unauthorized_probe: {
    status: number
    code: string
    success: boolean
  }
  commit_evidence: {
    receipt_id: string
    world_before_version: number
    world_after_version: number
    budget_before_sc: number
    budget_delta_sc: number
    budget_after_sc: number
  }
  verify_evidence: {
    receipt_id: string
    world_before_version: number
    world_after_version: number
    tick_count: number
  }
}

interface BenchmarkHost {
  execute(name: string, input: Record<string, unknown>): Promise<ToolResult>
  names(): string[]
}

interface BenchmarkTelemetryBridge {
  startTask(mode: BenchmarkMode): void
  record(event: string, fields?: Record<string, unknown>): void
  exportRows(): TelemetryRow[]
}

type BenchmarkWindow = Window & {
  __simverseWebMcpHost?: BenchmarkHost
  __simverseChallengeTelemetry?: BenchmarkTelemetryBridge
}

async function installBenchmarkRuntime(
  context: BrowserContext,
  withWebMcp: boolean,
): Promise<void> {
  await context.addInitScript((installWebMcp) => {
    type Tool = {
      name: string
      title?: string
      description: string
      inputSchema: Record<string, unknown>
      annotations?: Record<string, boolean>
      execute(
        input: Record<string, unknown>,
        options: { signal: AbortSignal },
      ): unknown | Promise<unknown>
    }
    const benchmarkGlobal = globalThis as typeof globalThis & {
      __SIMVERSE_CHALLENGE_BENCHMARK__?: true
    }
    benchmarkGlobal.__SIMVERSE_CHALLENGE_BENCHMARK__ = true
    if (!installWebMcp) return

    const tools = new Map<string, { tool: Tool; signal?: AbortSignal }>()
    const modelContext = new EventTarget() as EventTarget & {
      registerTool(tool: Tool, options?: { signal?: AbortSignal }): void
      getTools(): Promise<Array<Record<string, unknown>>>
    }
    modelContext.registerTool = (tool, options) => {
      const installed = { tool, signal: options?.signal }
      tools.set(tool.name, installed)
      options?.signal?.addEventListener('abort', () => {
        if (tools.get(tool.name) !== installed) return
        tools.delete(tool.name)
        modelContext.dispatchEvent(new Event('toolchange'))
      }, { once: true })
      modelContext.dispatchEvent(new Event('toolchange'))
    }
    modelContext.getTools = async () => [...tools.values()].map(({ tool }) => ({
      name: tool.name,
      title: tool.title,
      description: tool.description,
      inputSchema: tool.inputSchema,
      annotations: tool.annotations,
      origin: window.location.origin,
    }))
    Object.defineProperty(document, 'modelContext', {
      configurable: true,
      value: modelContext,
    })
    Object.defineProperty(navigator, 'modelContext', {
      configurable: true,
      value: modelContext,
    })
    const benchmarkWindow = window as BenchmarkWindow
    benchmarkWindow.__simverseWebMcpHost = {
      async execute(name, input) {
        const installed = tools.get(name)
        if (!installed) throw new Error(`Tool ${name} is not registered.`)
        return await installed.tool.execute(
          input,
          { signal: new AbortController().signal },
        ) as ToolResult
      },
      names: () => [...tools.keys()].sort(),
    }
  }, withWebMcp)
}

async function projection(page: Page): Promise<Projection> {
  return await page.evaluate(async (apiBase) => {
    const response = await fetch(`${apiBase}/challenge/session`, {
      credentials: 'include',
    })
    if (!response.ok) throw new Error(`Session GET failed with ${response.status}.`)
    return await response.json()
  }, API_BASE) as Projection
}

async function expectState(page: Page, state: string): Promise<void> {
  await expect(
    page.getByRole('region', { name: 'Challenge session status' })
      .getByText(state, { exact: true }),
  ).toBeVisible()
}

async function toolNames(page: Page): Promise<string[]> {
  return await page.evaluate(() => {
    const host = (window as BenchmarkWindow).__simverseWebMcpHost
    if (!host) throw new Error('Benchmark WebMCP host is unavailable.')
    return host.names()
  })
}

async function expectTools(page: Page, expected: string[]): Promise<void> {
  await expect.poll(() => toolNames(page)).toEqual([...expected].sort())
}

async function executeTool(
  page: Page,
  name: string,
  input: Record<string, unknown>,
): Promise<ToolResult> {
  return await page.evaluate(async ({ toolName, toolInput }) => {
    const host = (window as BenchmarkWindow).__simverseWebMcpHost
    if (!host) throw new Error('Benchmark WebMCP host is unavailable.')
    return await host.execute(toolName, toolInput)
  }, { toolName: name, toolInput: input })
}

async function startTelemetry(page: Page, mode: BenchmarkMode): Promise<void> {
  await page.evaluate((taskMode) => {
    const bridge = (window as BenchmarkWindow).__simverseChallengeTelemetry
    if (!bridge) throw new Error('Challenge benchmark telemetry bridge is unavailable.')
    bridge.startTask(taskMode)
  }, mode)
}

async function recordTelemetry(
  page: Page,
  event: string,
  fields: Record<string, unknown> = {},
): Promise<void> {
  await page.evaluate(({ eventName, safeFields }) => {
    const bridge = (window as BenchmarkWindow).__simverseChallengeTelemetry
    if (!bridge) throw new Error('Challenge benchmark telemetry bridge is unavailable.')
    bridge.record(eventName, safeFields)
  }, { eventName: event, safeFields: fields })
}

async function exportTelemetry(page: Page): Promise<TelemetryRow[]> {
  return await page.evaluate(() => {
    const bridge = (window as BenchmarkWindow).__simverseChallengeTelemetry
    if (!bridge) throw new Error('Challenge benchmark telemetry bridge is unavailable.')
    return bridge.exportRows()
  })
}

async function unauthorizedCommitProbe(
  page: Page,
  current: Projection,
): Promise<{ status: number; code: string; success: boolean }> {
  return await page.evaluate(async ({ apiBase, session }) => {
    if (!session.preview) throw new Error('Preview is missing before denial probe.')
    const response = await fetch(`${apiBase}/challenge/commit`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': session.csrf_token,
      },
      body: JSON.stringify({
        preview_id: session.preview.preview_id,
        expected_world_version: session.preview.based_on_world_version,
        diff_hash: session.preview.diff_hash,
      }),
    })
    const body = await response.json() as { error?: { code?: string } }
    return {
      status: response.status,
      code: body.error?.code ?? 'UNKNOWN',
      success: response.ok,
    }
  }, { apiBase: API_BASE, session: current })
}

function expectTelemetryRow(row: TelemetryRow, mode: BenchmarkMode): void {
  expect(row.mode).toBe(mode)
  expect(row.success).toBe(true)
  expect(row.clicks).toBe(mode === 'ordinary' ? 6 : 2)
  expect(row.panel_switches).toBe(2)
  expect(row.route_switches).toBe(1)
  expect(row.wrong_selections).toBe(0)
  expect(row.core_tool_calls).toBe(mode === 'ordinary' ? 0 : 4)
  expect(row.unauthorized_attempts).toBe(1)
  expect(row.unauthorized_successes).toBe(0)
  expect(row.preview_rebuild_count).toBe(0)
  expect(row.events.map(({ event }) => event)).toEqual(REQUIRED_EVENTS)
}

async function runBenchmarkRow(
  browser: Browser,
  mode: BenchmarkMode,
  pair: number,
): Promise<BenchmarkRow> {
  const context = await browser.newContext({ baseURL: 'http://localhost:4173' })
  await installBenchmarkRuntime(context, mode === 'webmcp')
  const page = await context.newPage()
  try {
    await page.goto('/challenge')
    await expectState(page, 'INITIAL')
    if (mode === 'webmcp') {
      await expect(page.getByText('Site Tools ready')).toBeVisible()
      await expectTools(page, [INVESTIGATE])
    } else {
      await expect(page.getByText('Site Tools unavailable')).toBeVisible()
    }

    await startTelemetry(page, mode)
    await recordTelemetry(page, 'panel_opened', {
      panel: 'living_world',
      route: 'challenge',
    })

    if (mode === 'ordinary') {
      await recordTelemetry(page, 'crisis_identified', { clicks: 1 })
      await page.getByRole('button', { name: 'Investigate Harbor crisis' }).click()
    } else {
      const investigated = await executeTool(page, INVESTIGATE, { budget_cap_sc: 300 })
      expect(investigated.state).toBe('EVIDENCE_READY')
    }
    await expectState(page, 'EVIDENCE_READY')
    await expect(page.getByText('Harbor focus active')).toBeVisible()

    if (mode === 'ordinary') {
      await recordTelemetry(page, 'preview_requested', { clicks: 1 })
      await page.getByRole('button', { name: 'Preview intervention' }).click()
    } else {
      await expectTools(page, [INVESTIGATE, PREVIEW])
      const previewed = await executeTool(page, PREVIEW, {
        crisis_id: 'harbor-wage-crisis',
        budget_cap_sc: 300,
      })
      expect(previewed.error).toBeUndefined()
      expect(previewed.preview_id).toBeTruthy()
    }
    await expectState(page, 'PREVIEW_READY')
    await expect(page.getByRole('region', { name: 'Review World Diff' })).toBeVisible()
    if (mode === 'webmcp') await expectTools(page, [PREVIEW])

    const previewedProjection = await projection(page)
    const unauthorizedProbe = await unauthorizedCommitProbe(page, previewedProjection)
    expect(unauthorizedProbe).toEqual({
      status: 403,
      code: 'APPROVAL_REQUIRED',
      success: false,
    })
    await recordTelemetry(page, 'approval_viewed', {
      panel: 'approval',
      unauthorized_attempts: 1,
    })
    await recordTelemetry(page, 'approval_granted', { clicks: 2 })
    await page.getByRole('checkbox', {
      name: 'I reviewed this exact World Diff.',
    }).check()
    await page.getByRole('button', { name: 'Create one-time approval' }).click()
    await expectState(page, 'APPROVED_ONCE')

    const approved = await projection(page)
    expect(approved.preview).not.toBeNull()
    const commitInput = {
      preview_id: approved.preview!.preview_id,
      expected_world_version: approved.preview!.based_on_world_version,
      diff_hash: approved.preview!.diff_hash,
    }
    if (mode === 'ordinary') {
      await recordTelemetry(page, 'commit_attempted', { clicks: 1 })
      await page.getByRole('button', { name: 'Commit approved intervention' }).click()
    } else {
      await expectTools(page, [COMMIT])
      const committedResult = await executeTool(page, COMMIT, commitInput)
      expect(committedResult.state).toBe('COMMITTED')
    }
    await expectState(page, 'COMMITTED')
    await expect(page.getByRole('region', { name: 'Execution Receipt' })).toBeVisible()
    const committed = await projection(page)
    expect(committed.receipt).not.toBeNull()
    expect(committed.world_version).toBe(8)
    expect(committed.budget_sc).toBe(60)

    if (mode === 'ordinary') {
      await recordTelemetry(page, 'verification_started', { clicks: 1 })
      await page.getByRole('button', { name: 'Verify 72-hour outcome' }).click()
    } else {
      await expectTools(page, [VERIFY])
      const verifiedResult = await executeTool(page, VERIFY, {
        receipt_id: committed.receipt!.receipt_id,
        advance_hours: 72,
      })
      expect(verifiedResult.state).toBe('VERIFIED')
    }
    await expectState(page, 'VERIFIED')
    await expect(page.getByRole('article', { name: 'Prediction' })).toBeVisible()
    await expect(page.getByRole('article', { name: 'Actual after 72h' })).toBeVisible()
    await expect(page.getByRole('article', { name: 'No-action control' })).toBeVisible()
    await expect(page.getByTestId('outcome-timeline-point')).toHaveCount(13)
    const verified = await projection(page)
    expect(verified.verification).not.toBeNull()
    await expect.poll(() => exportTelemetry(page)).toHaveLength(1)
    const [telemetry] = await exportTelemetry(page)
    expect(telemetry).toBeDefined()
    expectTelemetryRow(telemetry!, mode)

    return {
      ...telemetry!,
      run_id: `${mode}-${pair}`,
      unauthorized_probe: unauthorizedProbe,
      commit_evidence: {
        receipt_id: committed.receipt!.receipt_id,
        world_before_version: committed.receipt!.world_before_version,
        world_after_version: committed.receipt!.world_after_version,
        budget_before_sc: committed.receipt!.budget_before_sc,
        budget_delta_sc: committed.receipt!.budget_delta_sc,
        budget_after_sc: committed.receipt!.budget_after_sc,
      },
      verify_evidence: {
        receipt_id: verified.verification!.receipt_id,
        world_before_version: committed.world_version,
        world_after_version: verified.world_version,
        tick_count: verified.verification!.tick_snapshots.length,
      },
    }
  } finally {
    await context.close()
  }
}

test('records five paired ordinary and WebMCP challenge runs', async ({ browser }) => {
  const rows: BenchmarkRow[] = []
  for (let pair = 1; pair <= 5; pair += 1) {
    rows.push(await runBenchmarkRow(browser, 'ordinary', pair))
    rows.push(await runBenchmarkRow(browser, 'webmcp', pair))
  }

  expect(rows.filter(({ mode }) => mode === 'ordinary')).toHaveLength(5)
  expect(rows.filter(({ mode }) => mode === 'webmcp')).toHaveLength(5)
  expect(new Set(rows.map(({ run_id }) => run_id)).size).toBe(10)
  expect(rows.reduce((total, row) => total + row.unauthorized_successes, 0)).toBe(0)

  const sourceHead = execFileSync('git', ['rev-parse', 'HEAD'], {
    cwd: '..',
    encoding: 'utf8',
  }).trim()
  const temporaryPath = `${RAW_PATH}.tmp`
  writeFileSync(temporaryPath, JSON.stringify({
    schema_version: 1,
    recorded_at: new Date().toISOString(),
    source_head: sourceHead,
    chromium_version: browser.version(),
    rows,
  }, null, 2), { encoding: 'utf8', mode: 0o600 })
  renameSync(temporaryPath, RAW_PATH)
  console.log('ordinary_runs=5 webmcp_runs=5 paired_runs=5 unauthorized_success=0')
})
