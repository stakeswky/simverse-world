export type WebMcpSchemaScalar = string | number | boolean

export interface WebMcpInputSchema {
  readonly type: 'object' | 'string' | 'integer' | 'number' | 'boolean' | 'array'
  readonly properties?: Readonly<Record<string, WebMcpInputSchema>>
  readonly required?: readonly string[]
  readonly additionalProperties?: boolean
  readonly minimum?: number
  readonly maximum?: number
  readonly const?: WebMcpSchemaScalar
  readonly enum?: readonly WebMcpSchemaScalar[]
  readonly pattern?: string
  readonly items?: WebMcpInputSchema
}

export interface WebMcpRegistrationOptions {
  readonly signal?: AbortSignal
  readonly exposedTo?: readonly string[]
}

export interface WebMcpToolExecutionOptions {
  readonly signal?: AbortSignal
}

export interface RegisteredWebMcpTool {
  readonly name: string
  readonly title?: string
  readonly description: string
  readonly inputSchema?: WebMcpInputSchema
  readonly origin?: string
  readonly annotations?: {
    readonly readOnlyHint?: boolean
    readonly untrustedContentHint?: boolean
  }
}

export interface WebMcpToolDefinition {
  readonly name: string
  readonly title?: string
  readonly description: string
  readonly inputSchema: WebMcpInputSchema
  readonly annotations?: {
    readonly readOnlyHint?: boolean
    readonly untrustedContentHint?: boolean
  }
  readonly execute: (
    input: Record<string, unknown>,
    options?: WebMcpToolExecutionOptions,
  ) => unknown | Promise<unknown>
}

export interface WebMcpModelContext extends EventTarget {
  registerTool(
    definition: WebMcpToolDefinition,
    options?: WebMcpRegistrationOptions,
  ): void | Promise<void>
  getTools?(): Promise<readonly RegisteredWebMcpTool[]>
}

export type WebMcpDocument = Document & {
  readonly modelContext?: WebMcpModelContext
}

export type WebMcpNavigator = Navigator & {
  readonly modelContext?: WebMcpModelContext
}

function navigatorForDocument(toolDocument: Document): Navigator | undefined {
  if (toolDocument.defaultView) return toolDocument.defaultView.navigator
  if (typeof document !== 'undefined' && toolDocument === document && typeof navigator !== 'undefined') {
    return navigator
  }
  return undefined
}

export function getModelContext(
  toolDocument: Document,
  toolNavigator: Navigator | undefined = navigatorForDocument(toolDocument),
): WebMcpModelContext | undefined {
  const documentContext = (toolDocument as WebMcpDocument).modelContext
  if (documentContext) return documentContext
  return (toolNavigator as WebMcpNavigator | undefined)?.modelContext
}
