import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const API_BASE = 'http://localhost:8000'
const ARTIFACT_DIR = '/tmp/simverse-option-b-e2e-artifacts'
const INVESTIGATE = 'simverse_investigate_crisis'
const PREVIEW = 'simverse_preview_intervention'
const COMMIT = 'simverse_commit_approved'
const VERIFY = 'simverse_verify_outcome'
const RESET = 'simverse_reset_town'

interface Projection {
  session_generation: string
  state: string
  world_version: number
  world_hash: string
  budget_sc: number
  csrf_token: string
  tool_surface: string[]
  world: {
    events: Array<{ event_id: string }>
  }
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
    created_events: string[]
  }
}

interface ToolResult {
  state?: string
  receipt_id?: string
  world_hash?: string
  error?: { code?: string }
}

declare global {
  interface Window {
    __simverseWebMcpHost: {
      capture(name: string, alias: string): boolean
      duplicateCount(): number
      execute(name: string, input: Record<string, unknown>): Promise<ToolResult>
      executeCaptured(alias: string, input: Record<string, unknown>): Promise<ToolResult>
      names(): string[]
    }
  }
}

async function installWebMcpHost(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
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
    const tools = new Map<string, { tool: Tool; signal?: AbortSignal }>()
    const captured = new Map<string, Tool>()
    let duplicateRegistrations = 0
    const modelContext = new EventTarget() as EventTarget & {
      registerTool(tool: Tool, options?: { signal?: AbortSignal }): void
      getTools(): Promise<Array<Record<string, unknown>>>
    }
    modelContext.registerTool = (tool, options) => {
      if (tools.has(tool.name)) duplicateRegistrations += 1
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
    window.__simverseWebMcpHost = {
      capture(name, alias) {
        const installed = tools.get(name)
        if (!installed) return false
        captured.set(alias, installed.tool)
        return true
      },
      duplicateCount: () => duplicateRegistrations,
      async execute(name, input) {
        const installed = tools.get(name)
        if (!installed) throw new Error(`Tool ${name} is not registered.`)
        return await installed.tool.execute(
          input,
          { signal: new AbortController().signal },
        ) as ToolResult
      },
      async executeCaptured(alias, input) {
        const tool = captured.get(alias)
        if (!tool) throw new Error(`Captured tool ${alias} is missing.`)
        return await tool.execute(
          input,
          { signal: new AbortController().signal },
        ) as ToolResult
      },
      names: () => [...tools.keys()].sort(),
    }
  })
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

async function toolNames(page: Page): Promise<string[]> {
  return await page.evaluate(() => window.__simverseWebMcpHost.names())
}

async function expectTools(page: Page, expected: string[]): Promise<void> {
  await expect.poll(() => toolNames(page)).toEqual([...expected].sort())
}

async function executeTool(
  page: Page,
  name: string,
  input: Record<string, unknown>,
): Promise<ToolResult> {
  return await page.evaluate(
    async ({ toolName, toolInput }) => (
      await window.__simverseWebMcpHost.execute(toolName, toolInput)
    ),
    { toolName: name, toolInput: input },
  )
}

async function expectState(page: Page, state: string): Promise<void> {
  await expect(
    page.getByRole('region', { name: 'Challenge session status' })
      .getByText(state, { exact: true }),
  ).toBeVisible()
}

async function unauthorizedCommit(
  page: Page,
  current: Projection,
): Promise<{ status: number; body: ToolResult }> {
  return await page.evaluate(async ({ apiBase, session }) => {
    const preview = session.preview
    if (!preview) throw new Error('Preview is missing before unauthorized commit.')
    const response = await fetch(`${apiBase}/challenge/commit`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': session.csrf_token,
      },
      body: JSON.stringify({
        preview_id: preview.preview_id,
        expected_world_version: preview.based_on_world_version,
        diff_hash: preview.diff_hash,
      }),
    })
    return {
      status: response.status,
      body: await response.json(),
    }
  }, { apiBase: API_BASE, session: current }) as {
    status: number
    body: ToolResult
  }
}

async function browserReset(page: Page, current: Projection): Promise<Projection> {
  return await page.evaluate(async ({ apiBase, session }) => {
    const response = await fetch(`${apiBase}/challenge/reset`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': session.csrf_token,
      },
      body: JSON.stringify({ expected_generation: session.session_generation }),
    })
    if (!response.ok) throw new Error(`Reset failed with ${response.status}.`)
    return await response.json()
  }, { apiBase: API_BASE, session: current }) as Projection
}

test('runs ten real-browser challenge flows and ten same-context resets', async ({ browser }) => {
  mkdirSync(ARTIFACT_DIR, { recursive: true })
  console.log(`chromium_version=${browser.version()}`)
  let fullFlowCount = 0
  let resetHashCount = 0
  let replaySuccesses = 0
  let unauthorizedSuccesses = 0
  let duplicateTools = 0

  for (let run = 1; run <= 10; run += 1) {
    const context = await browser.newContext({ baseURL: 'http://localhost:4173' })
    await installWebMcpHost(context)
    const page = await context.newPage()
    const sessionRequests: string[] = []
    let successfulCommitResponses = 0
    page.on('request', (request) => {
      if (request.url() === `${API_BASE}/challenge/session`) {
        sessionRequests.push(request.method())
      }
    })
    page.on('response', (response) => {
      if (response.url() === `${API_BASE}/challenge/commit` && response.ok()) {
        successfulCommitResponses += 1
      }
    })

    await page.goto('/challenge')
    await expect(page.getByText('Site Tools ready')).toBeVisible()
    await expectState(page, 'INITIAL')
    await expectTools(page, [INVESTIGATE])
    await expect.poll(() => sessionRequests).toContain('GET')
    await expect.poll(() => sessionRequests).toContain('POST')
    const initial = await projection(page)
    const initialHash = initial.world_hash

    const investigated = await executeTool(page, INVESTIGATE, { budget_cap_sc: 300 })
    expect(investigated.state).toBe('EVIDENCE_READY')
    await expectState(page, 'EVIDENCE_READY')
    await expect(page.getByText('Harbor focus active')).toBeVisible()
    await expect(page.getByTestId('affected-resident')).toHaveCount(6)
    await expectTools(page, [INVESTIGATE, PREVIEW])

    const previewed = await executeTool(page, PREVIEW, {
      crisis_id: 'harbor-wage-crisis',
      budget_cap_sc: 300,
    })
    expect(previewed.error).toBeUndefined()
    await expectState(page, 'PREVIEW_READY')
    await expect(page.getByText('Immutable World Diff')).toBeVisible()
    await expect(page.getByText('Budget 300 SC → 60 SC')).toBeVisible()
    await expectTools(page, [PREVIEW])
    expect(await toolNames(page)).not.toContain(COMMIT)

    const beforeApproval = await projection(page)
    const unauthorized = await unauthorizedCommit(page, beforeApproval)
    if (unauthorized.body.state === 'COMMITTED') unauthorizedSuccesses += 1
    expect(unauthorized.status).toBe(403)
    expect(unauthorized.body.error?.code).toBe('APPROVAL_REQUIRED')

    await page.getByRole('checkbox', {
      name: 'I reviewed this exact World Diff.',
    }).check()
    await page.getByRole('button', { name: 'Create one-time approval' }).click()
    await expectState(page, 'APPROVED_ONCE')
    await expectTools(page, [COMMIT])
    expect(await page.evaluate((toolName) => (
      window.__simverseWebMcpHost.capture(toolName, 'approved-commit')
    ), COMMIT)).toBe(true)
    const approvalCookies = await context.cookies(`${API_BASE}/challenge/commit`)
    expect(approvalCookies).toEqual(expect.arrayContaining([
      expect.objectContaining({
        name: 'sv_challenge_approval',
        httpOnly: true,
        sameSite: 'Strict',
        path: '/challenge/commit',
      }),
    ]))

    const approved = await projection(page)
    expect(approved.world.events.filter((event) => (
      event.event_id === 'employer-escrow-mediation'
    ))).toHaveLength(0)
    const preview = approved.preview
    expect(preview).not.toBeNull()
    const commitInput = {
      preview_id: preview!.preview_id,
      expected_world_version: preview!.based_on_world_version,
      diff_hash: preview!.diff_hash,
    }
    let commitResults: ToolResult[]
    if (run === 1) {
      commitResults = await page.evaluate(async ({ name, input }) => (
        await Promise.all([
          window.__simverseWebMcpHost.execute(name, input),
          window.__simverseWebMcpHost.execute(name, input),
        ])
      ), { name: COMMIT, input: commitInput })
      expect(commitResults.filter((result) => result.state === 'COMMITTED')).toHaveLength(1)
      const replay = commitResults.find((result) => result.error?.code === 'APPROVAL_REPLAYED')
      expect(replay).toBeDefined()
      replaySuccesses += commitResults.filter((result) => (
        result.error?.code === 'APPROVAL_REPLAYED' && result.state === 'COMMITTED'
      )).length
    } else {
      commitResults = [await executeTool(page, COMMIT, commitInput)]
      expect(commitResults[0]?.state).toBe('COMMITTED')
    }

    await expectState(page, 'COMMITTED')
    await expectTools(page, [VERIFY])
    expect(await toolNames(page)).not.toContain(COMMIT)
    await expect(page.getByRole('region', { name: 'Execution Receipt' })).toBeVisible()
    await expect(page.getByText('Budget 300 − 240 → 60 SC')).toBeVisible()
    await expect(page.getByTestId('receipt-resident')).toHaveCount(6)
    await expect(page.getByRole('region', { name: 'Execution Receipt' })
      .getByText('employer-escrow-mediation')).toHaveCount(1)
    await expect.poll(() => successfulCommitResponses).toBe(1)
    const committed = await projection(page)
    expect(committed.world_version).toBe(8)
    expect(committed.budget_sc).toBe(60)
    expect(committed.receipt).toEqual(expect.objectContaining({
      world_before_version: 7,
      world_after_version: 8,
      budget_before_sc: 300,
      budget_delta_sc: -240,
      budget_after_sc: 60,
      created_events: ['employer-escrow-mediation'],
    }))
    expect(committed.world.events.filter((event) => (
      event.event_id === 'employer-escrow-mediation'
    ))).toHaveLength(1)

    const oldResult = await page.evaluate(async (input) => (
      await window.__simverseWebMcpHost.executeCaptured('approved-commit', input)
    ), commitInput)
    expect(oldResult.error?.code).toBe('STALE_TOOL_SURFACE')
    await page.waitForTimeout(25)
    expect(successfulCommitResponses).toBe(1)

    const verified = await executeTool(page, VERIFY, {
      receipt_id: committed.receipt!.receipt_id,
      advance_hours: 72,
    })
    expect(verified.state).toBe('VERIFIED')
    await expectState(page, 'VERIFIED')
    await expectTools(page, [RESET])
    await expect(page.getByRole('article', { name: 'Prediction' })).toBeVisible()
    await expect(page.getByRole('article', { name: 'Actual after 72h' })).toBeVisible()
    await expect(page.getByRole('article', { name: 'No-action control' })).toBeVisible()
    await expect(page.getByTestId('outcome-timeline-point')).toHaveCount(13)
    if (run === 10) {
      await page.setViewportSize({ width: 760, height: 1200 })
      const outcome = page.locator('.challenge-outcome')
      await outcome.scrollIntoViewIfNeeded()
      await outcome.screenshot({
        path: `${ARTIFACT_DIR}/challenge-full-flow-10.png`,
      })
      await page.getByRole('article', { name: 'Prediction' }).screenshot({
        path: `${ARTIFACT_DIR}/challenge-outcome-prediction.png`,
      })
      await page.getByRole('article', { name: 'Actual after 72h' }).screenshot({
        path: `${ARTIFACT_DIR}/challenge-outcome-actual.png`,
      })
      await page.getByRole('article', { name: 'No-action control' }).screenshot({
        path: `${ARTIFACT_DIR}/challenge-outcome-control.png`,
      })
    }

    const terminal = await projection(page)
    const resetResult = await executeTool(page, RESET, {
      expected_generation: terminal.session_generation,
    })
    expect(resetResult.state).toBe('INITIAL')
    await expectState(page, 'INITIAL')
    await expectTools(page, [INVESTIGATE])
    expect((await projection(page)).world_hash).toBe(initialHash)
    duplicateTools += await page.evaluate(() => (
      window.__simverseWebMcpHost.duplicateCount()
    ))
    fullFlowCount += 1

    await context.close()
  }

  const resetContext = await browser.newContext({ baseURL: 'http://localhost:4173' })
  await installWebMcpHost(resetContext)
  const resetPage = await resetContext.newPage()
  await resetPage.goto('/challenge')
  await expectState(resetPage, 'INITIAL')
  const resetInitialHash = (await projection(resetPage)).world_hash
  for (let reset = 1; reset <= 10; reset += 1) {
    const current = await projection(resetPage)
    const next = await browserReset(resetPage, current)
    expect(next.session_generation).not.toBe(current.session_generation)
    expect(next.world_version).toBe(7)
    expect(next.world_hash).toBe(resetInitialHash)
    resetHashCount += 1
  }
  await resetPage.reload()
  await expectState(resetPage, 'INITIAL')
  expect((await projection(resetPage)).world_hash).toBe(resetInitialHash)
  await resetPage.screenshot({
    fullPage: true,
    path: `${ARTIFACT_DIR}/challenge-reset-10.png`,
  })
  await resetContext.close()

  expect(fullFlowCount).toBe(10)
  expect(resetHashCount).toBe(10)
  expect(replaySuccesses).toBe(0)
  expect(unauthorizedSuccesses).toBe(0)
  expect(duplicateTools).toBe(0)
  console.log(
    'full_flow=10/10 reset_hash=10/10 replay_success=0 unauthorized_success=0 duplicate_tools=0',
  )
})
