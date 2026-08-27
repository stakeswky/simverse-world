import { useCallback, useSyncExternalStore } from 'react'

import {
  getAgentActivityHistory,
  subscribeToAgentActivity,
} from '../../webmcp/activity'

interface AgentActivityPanelProps {
  toolDocument?: Document
}

function currentDocument(): Document | undefined {
  return typeof document === 'undefined' ? undefined : document
}

const EMPTY_ACTIVITY = Object.freeze([])

export function AgentActivityPanel({
  toolDocument = currentDocument(),
}: AgentActivityPanelProps) {
  const subscribe = useCallback((listener: () => void) => {
    if (!toolDocument) return () => undefined
    return subscribeToAgentActivity(toolDocument, listener)
  }, [toolDocument])
  const getSnapshot = useCallback(
    () => toolDocument ? getAgentActivityHistory(toolDocument) : EMPTY_ACTIVITY,
    [toolDocument],
  )
  const entries = useSyncExternalStore(subscribe, getSnapshot, () => EMPTY_ACTIVITY)

  return (
    <section
      className="challenge-agent-activity"
      aria-label="Agent Activity"
    >
      <header>
        <div>
          <p>VISIBLE TOOL RECEIPTS</p>
          <h2>Agent Activity</h2>
        </div>
        <span>{entries.length}</span>
      </header>

      {entries.length === 0 ? (
        <div className="challenge-activity-empty">
          <i />
          <strong>No tool calls yet</strong>
          <span>Safe receipts will appear here when a Site Tool runs.</span>
        </div>
      ) : (
        <ol>
          {entries.map((entry) => (
            <li data-outcome={entry.outcome} key={entry.id}>
              <div className="challenge-activity-entry-head">
                <strong>{entry.toolName}</strong>
                <time dateTime={entry.occurredAt}>
                  {new Date(entry.occurredAt).toLocaleTimeString()}
                </time>
              </div>
              <span>{entry.phase} · {entry.outcome}</span>
              <dl>
                <div><dt>Duration</dt><dd>{entry.durationMs} ms</dd></div>
                <div><dt>Reason</dt><dd>{entry.reasonCode}</dd></div>
                <div>
                  <dt>World</dt>
                  <dd>World v{entry.worldVersionBefore} → v{entry.worldVersionAfter}</dd>
                </div>
                {entry.fingerprint ? (
                  <div><dt>Hash</dt><dd>{entry.fingerprint}</dd></div>
                ) : null}
                {entry.receiptId ? (
                  <div><dt>Receipt</dt><dd>{entry.receiptId}</dd></div>
                ) : null}
              </dl>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
