import { afterEach, describe, expect, it, vi } from 'vitest'
import { getAgentActivityHistory, resetAgentActivityForTests } from './activity'
import { getChallengeStatus } from './challengeStatus'
import type { WebMcpModelContext, WebMcpToolDefinition } from './types'
import {
  CHALLENGE_STATUS_TOOL_NAME,
  createChallengeStatusTool,
  registerChallengeStatusTool,
  resetWebMcpRegistrationsForTests,
} from './registerChallengeStatusTool'

function createToolDocument(registerTool?: WebMcpModelContext['registerTool']): Document {
  const toolDocument = document.implementation.createHTMLDocument('Challenge')
  if (registerTool) {
    Object.defineProperty(toolDocument, 'modelContext', {
      configurable: true,
      value: { registerTool },
    })
  }
  return toolDocument
}

function createToolNavigator(registerTool: WebMcpModelContext['registerTool']): Navigator {
  const toolNavigator = {} as Navigator
  Object.defineProperty(toolNavigator, 'modelContext', {
    configurable: true,
    value: { registerTool },
  })
  return toolNavigator
}

afterEach(() => {
  resetWebMcpRegistrationsForTests()
  resetAgentActivityForTests()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('registerChallengeStatusTool', () => {
  it('degrades safely when the browser does not support WebMCP', async () => {
    const toolDocument = createToolDocument()

    await expect(registerChallengeStatusTool({ document: toolDocument, enabled: true }))
      .resolves.toBe('unsupported')
  })

  it('registers through the Chrome 149 navigator.modelContext surface', async () => {
    const registerTool = vi.fn().mockResolvedValue(undefined)
    const toolDocument = createToolDocument()
    const toolNavigator = createToolNavigator(registerTool)

    await expect(registerChallengeStatusTool({
      document: toolDocument,
      navigator: toolNavigator,
      enabled: true,
    })).resolves.toBe('registered')

    expect(registerTool).toHaveBeenCalledTimes(1)
    expect(registerTool).toHaveBeenCalledWith(expect.objectContaining({
      name: CHALLENGE_STATUS_TOOL_NAME,
    }))
  })

  it('degrades safely when WebMCP feature detection itself throws', async () => {
    const toolDocument = createToolDocument()
    Object.defineProperty(toolDocument, 'modelContext', {
      configurable: true,
      get: () => { throw new Error('Authorization: Bearer feature-secret') },
    })

    await expect(registerChallengeStatusTool({ document: toolDocument, enabled: true }))
      .resolves.toBe('unsupported')
  })

  it('degrades safely when the registerTool capability getter throws', async () => {
    const toolDocument = createToolDocument()
    const modelContext = {}
    Object.defineProperty(modelContext, 'registerTool', {
      configurable: true,
      get: () => { throw new Error('Authorization: Bearer capability-secret') },
    })
    Object.defineProperty(toolDocument, 'modelContext', {
      configurable: true,
      value: modelContext,
    })

    await expect(registerChallengeStatusTool({ document: toolDocument, enabled: true }))
      .resolves.toBe('unsupported')
  })

  it('does not register when VITE_WEBMCP_ENABLED is off', async () => {
    vi.stubEnv('VITE_WEBMCP_ENABLED', 'false')
    const registerTool = vi.fn()
    const toolDocument = createToolDocument(registerTool)

    await expect(registerChallengeStatusTool({ document: toolDocument })).resolves.toBe('disabled')
    expect(registerTool).not.toHaveBeenCalled()
  })

  it('deduplicates repeated mounts for the same document', async () => {
    const registerTool = vi.fn().mockResolvedValue(undefined)
    const toolDocument = createToolDocument(registerTool)

    const states = await Promise.all([
      registerChallengeStatusTool({ document: toolDocument, enabled: true }),
      registerChallengeStatusTool({ document: toolDocument, enabled: true }),
      registerChallengeStatusTool({ document: toolDocument, enabled: true }),
    ])

    expect(states).toEqual(['registered', 'registered', 'registered'])
    expect(registerTool).toHaveBeenCalledTimes(1)
  })

  it('registers again for a fresh document after a page refresh', async () => {
    const firstRegister = vi.fn()
    const secondRegister = vi.fn()

    await expect(registerChallengeStatusTool({
      document: createToolDocument(firstRegister),
      enabled: true,
    })).resolves.toBe('registered')
    await expect(registerChallengeStatusTool({
      document: createToolDocument(secondRegister),
      enabled: true,
    })).resolves.toBe('registered')

    expect(firstRegister).toHaveBeenCalledTimes(1)
    expect(secondRegister).toHaveBeenCalledTimes(1)
  })

  it('allows a safe retry after registration fails', async () => {
    const registerTool = vi.fn()
      .mockRejectedValueOnce(new Error('Authorization: Bearer registration-secret'))
      .mockResolvedValueOnce(undefined)
    const toolDocument = createToolDocument(registerTool)

    await expect(registerChallengeStatusTool({ document: toolDocument, enabled: true }))
      .resolves.toBe('failed')
    await expect(registerChallengeStatusTool({ document: toolDocument, enabled: true }))
      .resolves.toBe('registered')

    expect(registerTool).toHaveBeenCalledTimes(2)
  })

  it('registers a narrow, read-only tool with a stable result', async () => {
    let registeredTool: WebMcpToolDefinition | undefined
    const registerTool = vi.fn((tool: WebMcpToolDefinition) => {
      registeredTool = tool
    })
    const toolDocument = createToolDocument(registerTool)

    await expect(registerChallengeStatusTool({ document: toolDocument, enabled: true }))
      .resolves.toBe('registered')

    expect(registeredTool).toMatchObject({
      name: CHALLENGE_STATUS_TOOL_NAME,
      inputSchema: { type: 'object', properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true },
    })
    await expect(registeredTool?.execute({})).resolves.toEqual(getChallengeStatus())
    await expect(registeredTool?.execute({})).resolves.toEqual(getChallengeStatus())
    await expect(registeredTool?.execute({ unexpected: true })).resolves.toEqual({
      error: {
        code: 'invalid_input',
        message: 'Tool input must be an empty object.',
      },
    })
  })

  it('returns a generic error without leaking credentials or internal stacks', async () => {
    const sensitiveError = new Error('Authorization: Bearer jwt-secret-token')
    sensitiveError.stack = 'internal/server/private.ts:42 token=jwt-secret-token'
    const toolDocument = createToolDocument()
    const tool = createChallengeStatusTool({
      document: toolDocument,
      statusProvider: () => { throw sensitiveError },
      clock: vi.fn().mockReturnValueOnce(10).mockReturnValueOnce(12),
    })
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    const result = await tool.execute({})
    const serialized = JSON.stringify({
      result,
      activity: getAgentActivityHistory(toolDocument),
    })

    expect(result).toEqual({
      error: {
        code: 'challenge_status_unavailable',
        message: 'Challenge status is temporarily unavailable.',
      },
    })
    expect(serialized).not.toMatch(/jwt-secret-token|Authorization|Bearer|private\.ts|stack/i)
    expect(consoleError).not.toHaveBeenCalled()
  })

  it('records a fixed failed receipt for invalid input without retaining the input', async () => {
    const toolDocument = createToolDocument()
    const tool = createChallengeStatusTool({ document: toolDocument, clock: () => 10 })

    await expect(tool.execute({ Authorization: 'Bearer input-secret' })).resolves.toEqual({
      error: {
        code: 'invalid_input',
        message: 'Tool input must be an empty object.',
      },
    })

    const serialized = JSON.stringify(getAgentActivityHistory(toolDocument))
    expect(serialized).toContain('failed')
    expect(serialized).not.toMatch(/input-secret|Authorization|Bearer/i)
  })
})
