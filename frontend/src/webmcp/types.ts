export interface WebMcpInputSchema {
  readonly type: 'object'
  readonly properties: Readonly<Record<string, unknown>>
  readonly additionalProperties: false
}

export interface WebMcpToolDefinition {
  readonly name: string
  readonly description: string
  readonly inputSchema: WebMcpInputSchema
  readonly annotations?: {
    readonly readOnlyHint?: boolean
  }
  readonly execute: (input?: unknown) => unknown | Promise<unknown>
}

export interface WebMcpRegistrationOptions {
  readonly signal?: AbortSignal
}

export interface WebMcpModelContext {
  registerTool(
    definition: WebMcpToolDefinition,
    options?: WebMcpRegistrationOptions,
  ): void | Promise<void>
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
