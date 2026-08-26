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

export interface WebMcpModelContext {
  registerTool(definition: WebMcpToolDefinition): void | Promise<void>
}

export type WebMcpDocument = Document & {
  readonly modelContext?: WebMcpModelContext
}

export function getModelContext(toolDocument: Document): WebMcpModelContext | undefined {
  return (toolDocument as WebMcpDocument).modelContext
}
