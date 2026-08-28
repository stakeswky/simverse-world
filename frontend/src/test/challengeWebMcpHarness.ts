import type { ChallengeProjection } from '../services/api/challenge'
import type {
  RegisteredWebMcpTool,
  WebMcpModelContext,
  WebMcpRegistrationOptions,
  WebMcpToolDefinition,
  WebMcpToolExecutionOptions,
} from '../webmcp/types'

export interface HarnessRegistrationCall {
  readonly definition: WebMcpToolDefinition
  readonly options: WebMcpRegistrationOptions | undefined
}

interface InstalledTool {
  readonly definition: WebMcpToolDefinition
  readonly signal: AbortSignal | undefined
}

class HarnessModelContext extends EventTarget implements WebMcpModelContext {
  private readonly harness: ChallengeWebMcpHarness

  constructor(harness: ChallengeWebMcpHarness) {
    super()
    this.harness = harness
  }

  registerTool(
    definition: WebMcpToolDefinition,
    options?: WebMcpRegistrationOptions,
  ): void | Promise<void> {
    return this.harness.registerTool(definition, options)
  }

  getTools(): Promise<readonly RegisteredWebMcpTool[]> {
    return this.harness.getTools()
  }
}

export interface ChallengeWebMcpHarnessOptions {
  readonly supportsGetTools?: boolean
  readonly unregisterDelayMs?: number
  readonly retainToolsOnAbort?: boolean
}

export class ChallengeWebMcpHarness {
  readonly modelContext: WebMcpModelContext
  readonly registrationCalls: HarnessRegistrationCall[] = []
  reloadCount = 0
  getToolsCalls = 0

  private readonly tools = new Map<string, InstalledTool>()
  private readonly registrationOutcomes: Array<void | Promise<void>> = []
  private readonly unregisterDelayMs: number
  private readonly retainToolsOnAbort: boolean

  constructor(options: ChallengeWebMcpHarnessOptions = {}) {
    const context = new HarnessModelContext(this)
    if (options.supportsGetTools === false) {
      Object.defineProperty(context, 'getTools', {
        configurable: true,
        value: undefined,
      })
    }
    this.modelContext = context
    this.unregisterDelayMs = options.unregisterDelayMs ?? 0
    this.retainToolsOnAbort = options.retainToolsOnAbort ?? false
  }

  readonly reload = (): void => {
    this.reloadCount += 1
  }

  queueRegistrationOutcome(outcome: void | Promise<void>): void {
    this.registrationOutcomes.push(outcome)
  }

  registerTool(
    definition: WebMcpToolDefinition,
    options?: WebMcpRegistrationOptions,
  ): void | Promise<void> {
    this.registrationCalls.push({ definition, options })
    const outcome = this.registrationOutcomes.shift()
    if (outcome instanceof Promise) {
      return outcome.then(() => this.install(definition, options?.signal))
    }
    this.install(definition, options?.signal)
  }

  async getTools(): Promise<readonly RegisteredWebMcpTool[]> {
    this.getToolsCalls += 1
    return [...this.tools.values()].map(({ definition }) => ({
      name: definition.name,
      title: definition.title,
      description: definition.description,
      inputSchema: definition.inputSchema,
      annotations: definition.annotations,
      origin: 'https://simverse.world',
    }))
  }

  tool(name: string): WebMcpToolDefinition | undefined {
    return this.tools.get(name)?.definition
  }

  toolNames(): string[] {
    return [...this.tools.keys()].sort()
  }

  execute(
    name: string,
    input: Record<string, unknown>,
    options: WebMcpToolExecutionOptions,
  ): unknown | Promise<unknown> {
    const tool = this.tool(name)
    if (!tool) throw new Error(`Tool ${name} is not registered.`)
    return tool.execute(input, options)
  }

  dispatchToolChange(): void {
    this.modelContext.dispatchEvent(new Event('toolchange'))
  }

  private install(
    definition: WebMcpToolDefinition,
    signal: AbortSignal | undefined,
  ): void {
    if (signal?.aborted) return
    const installed = { definition, signal }
    this.tools.set(definition.name, installed)
    signal?.addEventListener('abort', () => {
      if (this.retainToolsOnAbort) return
      const remove = () => {
        if (this.tools.get(definition.name) !== installed) return
        this.tools.delete(definition.name)
        this.dispatchToolChange()
      }
      if (this.unregisterDelayMs > 0) {
        window.setTimeout(remove, this.unregisterDelayMs)
      } else {
        remove()
      }
    }, { once: true })
    this.dispatchToolChange()
  }
}

export function challengeProjection(
  overrides: Partial<ChallengeProjection> = {},
): ChallengeProjection {
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
    csrf_token: 'csrf-test-only',
    world: {} as ChallengeProjection['world'],
    evidence: null,
    preview: null,
    approval_fingerprint: null,
    approval_expires_at: null,
    receipt: null,
    verification: null,
    ...overrides,
  }
}
