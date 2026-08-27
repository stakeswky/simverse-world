export const CHALLENGE_TELEMETRY_EVENTS = [
  'task_started',
  'panel_opened',
  'wrong_target_selected',
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

export type ChallengeTelemetryEvent = typeof CHALLENGE_TELEMETRY_EVENTS[number]
export type ChallengeTelemetryMode = 'ordinary' | 'webmcp'
export type ChallengeTelemetryPanel =
  | 'living_world'
  | 'decision_flow'
  | 'approval'
  | 'outcome'
  | 'agent_activity'
export type ChallengeTelemetryRoute =
  | 'challenge'
  | 'direct'
  | 'back_forward'
  | 'same_document'
export type ChallengeTelemetryWrongSelection = 'resident' | 'region'

export interface ChallengeTelemetrySafeFields {
  duration_ms?: number
  clicks?: number
  panel?: ChallengeTelemetryPanel
  route?: ChallengeTelemetryRoute
  wrong_selection?: ChallengeTelemetryWrongSelection
  success?: boolean
  core_tool_calls?: number
  unauthorized_attempts?: number
  unauthorized_successes?: number
  preview_rebuild_count?: number
}

export interface ChallengeTelemetryEventRecord {
  event: ChallengeTelemetryEvent
  elapsed_ms: number
  fields: ChallengeTelemetrySafeFields
}

export interface ChallengeTelemetryRow {
  run_id: string
  mode: ChallengeTelemetryMode
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
  events: ChallengeTelemetryEventRecord[]
}

export interface ChallengeTelemetryRecorderOptions {
  clock?: () => number
  idFactory?: () => string
}

export interface ChallengeTelemetryRecorder {
  startTask(mode: ChallengeTelemetryMode): void
  record(
    event: ChallengeTelemetryEvent,
    safeFields?: ChallengeTelemetrySafeFields,
  ): void
  completeTask(): ChallengeTelemetryRow | null
  exportRows(): ChallengeTelemetryRow[]
  resetForTests(): void
}

export type ChallengeTelemetryBenchmarkBridge = Pick<
  ChallengeTelemetryRecorder,
  'startTask' | 'record' | 'completeTask' | 'exportRows'
>

interface ActiveTelemetryRow extends ChallengeTelemetryRow {
  started_at_ms: number
}

const EVENT_NAMES = new Set<string>(CHALLENGE_TELEMETRY_EVENTS)
const SAFE_FIELD_NAMES = new Set<keyof ChallengeTelemetrySafeFields>([
  'duration_ms',
  'clicks',
  'panel',
  'route',
  'wrong_selection',
  'success',
  'core_tool_calls',
  'unauthorized_attempts',
  'unauthorized_successes',
  'preview_rebuild_count',
])
const PANELS = new Set<ChallengeTelemetryPanel>([
  'living_world',
  'decision_flow',
  'approval',
  'outcome',
  'agent_activity',
])
const ROUTES = new Set<ChallengeTelemetryRoute>([
  'challenge',
  'direct',
  'back_forward',
  'same_document',
])
const WRONG_SELECTIONS = new Set<ChallengeTelemetryWrongSelection>([
  'resident',
  'region',
])

let fallbackId = 0

function monotonicNow(): number {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now()
  }
  return Date.now()
}

function defaultIdFactory(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  fallbackId += 1
  return `challenge-run-${Date.now()}-${fallbackId}`
}

function nonNegativeNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new TypeError(`${field} must be a finite non-negative number.`)
  }
  return value
}

function sanitizeSafeFields(
  input: ChallengeTelemetrySafeFields | undefined,
): ChallengeTelemetrySafeFields {
  if (input === undefined) return {}
  if (input === null || typeof input !== 'object' || Array.isArray(input)) {
    throw new TypeError('Telemetry fields must be an object.')
  }
  for (const field of Object.keys(input)) {
    if (!SAFE_FIELD_NAMES.has(field as keyof ChallengeTelemetrySafeFields)) {
      throw new TypeError(`Unsafe telemetry field: ${field}.`)
    }
  }

  const safe: ChallengeTelemetrySafeFields = {}
  if (input.duration_ms !== undefined) {
    safe.duration_ms = nonNegativeNumber(input.duration_ms, 'duration_ms')
  }
  if (input.clicks !== undefined) {
    safe.clicks = nonNegativeNumber(input.clicks, 'clicks')
  }
  if (input.panel !== undefined) {
    if (!PANELS.has(input.panel)) throw new TypeError('Invalid panel value.')
    safe.panel = input.panel
  }
  if (input.route !== undefined) {
    if (!ROUTES.has(input.route)) throw new TypeError('Invalid route value.')
    safe.route = input.route
  }
  if (input.wrong_selection !== undefined) {
    if (!WRONG_SELECTIONS.has(input.wrong_selection)) {
      throw new TypeError('Invalid wrong_selection value.')
    }
    safe.wrong_selection = input.wrong_selection
  }
  if (input.success !== undefined) {
    if (typeof input.success !== 'boolean') {
      throw new TypeError('success must be boolean.')
    }
    safe.success = input.success
  }
  if (input.core_tool_calls !== undefined) {
    safe.core_tool_calls = nonNegativeNumber(
      input.core_tool_calls,
      'core_tool_calls',
    )
  }
  if (input.unauthorized_attempts !== undefined) {
    safe.unauthorized_attempts = nonNegativeNumber(
      input.unauthorized_attempts,
      'unauthorized_attempts',
    )
  }
  if (input.unauthorized_successes !== undefined) {
    safe.unauthorized_successes = nonNegativeNumber(
      input.unauthorized_successes,
      'unauthorized_successes',
    )
  }
  if (input.preview_rebuild_count !== undefined) {
    safe.preview_rebuild_count = nonNegativeNumber(
      input.preview_rebuild_count,
      'preview_rebuild_count',
    )
  }
  return safe
}

function cloneEvent(record: ChallengeTelemetryEventRecord): ChallengeTelemetryEventRecord {
  return {
    event: record.event,
    elapsed_ms: record.elapsed_ms,
    fields: { ...record.fields },
  }
}

function cloneRow(row: ChallengeTelemetryRow): ChallengeTelemetryRow {
  return {
    ...row,
    events: row.events.map(cloneEvent),
  }
}

function mergeEventFields(
  current: ChallengeTelemetrySafeFields,
  next: ChallengeTelemetrySafeFields,
): ChallengeTelemetrySafeFields {
  const merged: ChallengeTelemetrySafeFields = { ...current, ...next }
  const additiveFields = [
    'clicks',
    'core_tool_calls',
    'unauthorized_attempts',
    'unauthorized_successes',
    'preview_rebuild_count',
  ] as const
  for (const field of additiveFields) {
    if (current[field] !== undefined || next[field] !== undefined) {
      merged[field] = (current[field] ?? 0) + (next[field] ?? 0)
    }
  }
  return merged
}

export function createChallengeTelemetryRecorder(
  options: ChallengeTelemetryRecorderOptions = {},
): ChallengeTelemetryRecorder {
  const clock = options.clock ?? monotonicNow
  const idFactory = options.idFactory ?? defaultIdFactory
  const completedRows: ChallengeTelemetryRow[] = []
  let active: ActiveTelemetryRow | null = null

  const record = (
    event: ChallengeTelemetryEvent,
    safeFields?: ChallengeTelemetrySafeFields,
  ): void => {
    if (!EVENT_NAMES.has(event)) {
      throw new TypeError(`Invalid challenge telemetry event: ${String(event)}.`)
    }
    if (!active) return
    const fields = sanitizeSafeFields(safeFields)
    const elapsedMs = Math.max(0, clock() - active.started_at_ms)
    const previous = active.events[active.events.length - 1]
    if (previous?.event === event) {
      previous.elapsed_ms = elapsedMs
      previous.fields = mergeEventFields(previous.fields, fields)
    } else {
      active.events.push({ event, elapsed_ms: elapsedMs, fields })
    }
    active.clicks += fields.clicks ?? 0
    active.panel_switches += fields.panel === undefined ? 0 : 1
    active.route_switches += fields.route === undefined ? 0 : 1
    active.wrong_selections += fields.wrong_selection === undefined ? 0 : 1
    if (fields.success !== undefined) active.success = fields.success
    if (active.mode === 'webmcp') {
      active.core_tool_calls += fields.core_tool_calls ?? 0
    }
    active.unauthorized_attempts += fields.unauthorized_attempts ?? 0
    active.unauthorized_successes += fields.unauthorized_successes ?? 0
    active.preview_rebuild_count += fields.preview_rebuild_count ?? 0
  }

  return {
    startTask(mode): void {
      if (mode !== 'ordinary' && mode !== 'webmcp') {
        throw new TypeError(`Invalid challenge telemetry mode: ${String(mode)}.`)
      }
      if (active) throw new Error('A challenge telemetry task is already active.')
      const startedAt = clock()
      active = {
        run_id: idFactory(),
        mode,
        started_at_ms: startedAt,
        duration_ms: 0,
        clicks: 0,
        panel_switches: 0,
        route_switches: 0,
        wrong_selections: 0,
        success: false,
        core_tool_calls: 0,
        unauthorized_attempts: 0,
        unauthorized_successes: 0,
        preview_rebuild_count: 0,
        events: [],
      }
      record('task_started')
    },

    record,

    completeTask(): ChallengeTelemetryRow | null {
      if (!active) return null
      record('task_completed', { success: true })
      active.duration_ms = Math.max(0, clock() - active.started_at_ms)
      const row: ChallengeTelemetryRow = {
        run_id: active.run_id,
        mode: active.mode,
        duration_ms: active.duration_ms,
        clicks: active.clicks,
        panel_switches: active.panel_switches,
        route_switches: active.route_switches,
        wrong_selections: active.wrong_selections,
        success: active.success,
        core_tool_calls: active.core_tool_calls,
        unauthorized_attempts: active.unauthorized_attempts,
        unauthorized_successes: active.unauthorized_successes,
        preview_rebuild_count: active.preview_rebuild_count,
        events: active.events.map(cloneEvent),
      }
      completedRows.push(row)
      active = null
      return cloneRow(row)
    },

    exportRows(): ChallengeTelemetryRow[] {
      return completedRows.map(cloneRow)
    },

    resetForTests(): void {
      active = null
      completedRows.splice(0, completedRows.length)
    },
  }
}

export const challengeTelemetry = createChallengeTelemetryRecorder()

declare global {
  var __SIMVERSE_CHALLENGE_BENCHMARK__: true | undefined
  var __simverseChallengeTelemetry: ChallengeTelemetryBenchmarkBridge | undefined
}

export function installChallengeTelemetryBenchmarkBridge(): void {
  if (globalThis.__SIMVERSE_CHALLENGE_BENCHMARK__ !== true) {
    delete globalThis.__simverseChallengeTelemetry
    return
  }

  globalThis.__simverseChallengeTelemetry = {
    startTask: (mode) => challengeTelemetry.startTask(mode),
    record: (event, safeFields) => challengeTelemetry.record(event, safeFields),
    completeTask: () => challengeTelemetry.completeTask(),
    exportRows: () => challengeTelemetry.exportRows(),
  }
}

installChallengeTelemetryBenchmarkBridge()
