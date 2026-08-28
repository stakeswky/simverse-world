export type AgentActivityOutcome = 'completed' | 'failed'
export type AgentActivityPhase =
  | 'status'
  | 'investigate'
  | 'preview'
  | 'commit'
  | 'verify'
  | 'reset'

export interface PublishAgentActivityInput {
  readonly toolName: string
  readonly phase: AgentActivityPhase
  readonly outcome: AgentActivityOutcome
  readonly durationMs: number
  readonly reasonCode: string
  readonly worldVersionBefore: number
  readonly worldVersionAfter: number
  readonly receiptId: string | null
  readonly fingerprint: string | null
}

export interface AgentActivityEntry extends PublishAgentActivityInput {
  readonly id: string
  readonly occurredAt: string
}

interface ActivityStore {
  entries: readonly AgentActivityEntry[]
  readonly listeners: Set<() => void>
}

const EMPTY_ACTIVITY: readonly AgentActivityEntry[] = Object.freeze([])
let activitySequence = 0
let activityStores = new WeakMap<Document, ActivityStore>()

function getActivityStore(toolDocument: Document): ActivityStore {
  const existing = activityStores.get(toolDocument)
  if (existing) return existing
  const created: ActivityStore = { entries: EMPTY_ACTIVITY, listeners: new Set() }
  activityStores.set(toolDocument, created)
  return created
}

export function publishAgentActivity(
  toolDocument: Document,
  activity: PublishAgentActivityInput,
): AgentActivityEntry {
  activitySequence += 1
  const entry: AgentActivityEntry = Object.freeze({
    ...activity,
    id: `webmcp-${Date.now()}-${activitySequence}`,
    occurredAt: new Date().toISOString(),
  })
  const store = getActivityStore(toolDocument)
  store.entries = Object.freeze([entry, ...store.entries].slice(0, 20))
  for (const listener of store.listeners) {
    try {
      listener()
    } catch {
      // One broken subscriber must not suppress other receipts or fail the tool.
    }
  }
  return entry
}

export function getAgentActivityHistory(toolDocument: Document): readonly AgentActivityEntry[] {
  return activityStores.get(toolDocument)?.entries ?? EMPTY_ACTIVITY
}

/** Test isolation only. Production history is scoped to the current document. */
export function resetAgentActivityForTests(): void {
  activityStores = new WeakMap<Document, ActivityStore>()
  activitySequence = 0
}

export function subscribeToAgentActivity(
  toolDocument: Document,
  listener: () => void,
): () => void {
  const store = getActivityStore(toolDocument)
  store.listeners.add(listener)
  return () => store.listeners.delete(listener)
}
