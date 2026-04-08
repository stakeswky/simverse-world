import { useCallback, useEffect, useState } from 'react'
import { getAdminForgeActive, getAdminForgeHistory } from '../../services/api'
import type { AdminForgeSession, AdminForgeHistoryItem } from '../../services/api'

// ─── Stage badge ─────────────────────────────────────────────────

const STAGE_COLORS: Record<string, { bg: string; color: string }> = {
  routing:     { bg: 'rgba(107,114,128,0.15)', color: '#9ca3af' },
  researching: { bg: 'rgba(59,130,246,0.15)',  color: '#60a5fa' },
  extracting:  { bg: 'rgba(99,102,241,0.15)',  color: '#818cf8' },
  building:    { bg: 'rgba(139,92,246,0.15)',  color: '#a78bfa' },
  validating:  { bg: 'rgba(34,197,94,0.15)',   color: '#4ade80' },
  refining:    { bg: 'rgba(20,184,166,0.15)',  color: '#2dd4bf' },
  done:        { bg: 'rgba(34,197,94,0.15)',   color: '#4ade80' },
  error:       { bg: 'rgba(233,69,96,0.15)',   color: '#e94560' },
  collecting:  { bg: 'rgba(249,115,22,0.15)',  color: '#fb923c' },
  generating:  { bg: 'rgba(234,179,8,0.15)',   color: '#facc15' },
}

const STAGE_LABELS: Record<string, string> = {
  routing:    '路由中',
  researching:'调研中',
  extracting: '提取中',
  building:   '构建中',
  validating: '验证中',
  refining:   '精炼中',
  done:       '完成',
  error:      '错误',
  collecting: '收集中',
  generating: '生成中',
}

function StageBadge({ stage }: { stage: string }) {
  const colors = STAGE_COLORS[stage] ?? { bg: 'rgba(107,114,128,0.15)', color: '#9ca3af' }
  return (
    <span style={{
      fontSize: 11,
      padding: '2px 8px',
      borderRadius: 4,
      background: colors.bg,
      color: colors.color,
      fontWeight: 600,
      whiteSpace: 'nowrap',
    }}>
      {STAGE_LABELS[stage] ?? stage}
    </span>
  )
}

function ModeBadge({ mode }: { mode: 'quick' | 'deep' }) {
  return (
    <span style={{
      fontSize: 11,
      padding: '2px 8px',
      borderRadius: 4,
      background: mode === 'deep' ? 'rgba(139,92,246,0.15)' : 'rgba(59,130,246,0.15)',
      color: mode === 'deep' ? '#a78bfa' : '#60a5fa',
      fontWeight: 600,
    }}>
      {mode === 'deep' ? '深度' : '快速'}
    </span>
  )
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

// ─── Active Sessions ──────────────────────────────────────────────

interface ActiveSessionsProps {
  token: string
}

function ActiveSessions({ token }: ActiveSessionsProps) {
  const [sessions, setSessions] = useState<AdminForgeSession[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchSessions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAdminForgeActive(token)
      setSessions(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void fetchSessions()
    const interval = setInterval(() => void fetchSessions(), 10000)
    return () => clearInterval(interval)
  }, [fetchSessions])

  if (loading && sessions.length === 0) {
    return (
      <div style={{ color: 'var(--text-muted)', padding: '20px 0', textAlign: 'center' }}>
        加载中...
      </div>
    )
  }

  if (error) {
    return (
      <div style={{
        background: 'rgba(233,69,96,0.1)',
        border: '1px solid rgba(233,69,96,0.3)',
        borderRadius: 6,
        padding: '8px 12px',
        fontSize: 13,
        color: '#e94560',
      }}>
        {error}
      </div>
    )
  }

  if (sessions.length === 0) {
    return (
      <div style={{ color: 'var(--text-muted)', padding: '20px 0', textAlign: 'center', fontSize: 13 }}>
        当前无活跃会话
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
      {sessions.map((s) => (
        <div
          key={s.forge_id}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 10,
            padding: '14px 16px',
            minWidth: 220,
            flex: '1 1 220px',
            maxWidth: 320,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>{s.character_name}</div>
            <ModeBadge mode={s.mode} />
          </div>
          <div style={{ marginBottom: 8 }}>
            <StageBadge stage={s.current_stage} />
          </div>
          <div style={{ display: 'flex', gap: 12, fontSize: 12, color: 'var(--text-muted)' }}>
            <span>耗时 {formatElapsed(s.elapsed_seconds)}</span>
            <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.7 }}>{s.forge_id.slice(0, 8)}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── History Table ────────────────────────────────────────────────

const HISTORY_STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'done', label: '完成' },
  { value: 'error', label: '错误' },
  { value: 'generating', label: '生成中' },
  { value: 'collecting', label: '收集中' },
]

interface HistoryTableProps {
  token: string
}

function HistoryTable({ token }: HistoryTableProps) {
  const [items, setItems] = useState<AdminForgeHistoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [perPage] = useState(20)
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchHistory = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await getAdminForgeHistory(token, {
        page,
        per_page: perPage,
        status: statusFilter || undefined,
      })
      setItems(resp.items)
      setTotal(resp.total)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [token, page, perPage, statusFilter])

  useEffect(() => {
    void fetchHistory()
  }, [fetchHistory])

  const totalPages = Math.ceil(total / perPage)

  const selectStyle: React.CSSProperties = {
    padding: '7px 11px',
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    color: 'white',
    fontSize: 13,
    outline: 'none',
    cursor: 'pointer',
  }

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 12, alignItems: 'center' }}>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
          style={selectStyle}
        >
          {HISTORY_STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>
          共 {total} 条
        </div>
      </div>

      {error && (
        <div style={{
          background: 'rgba(233,69,96,0.1)',
          border: '1px solid rgba(233,69,96,0.3)',
          borderRadius: 6,
          padding: '8px 12px',
          fontSize: 13,
          color: '#e94560',
          marginBottom: 12,
        }}>
          {error}
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['角色名', '模式', '状态', '最终阶段', '开始时间', '结束时间', '居民 ID'].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: '8px 12px',
                    textAlign: 'left',
                    color: 'var(--text-muted)',
                    fontWeight: 600,
                    fontSize: 12,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
                  加载中...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
                  暂无记录
                </td>
              </tr>
            ) : items.map((item) => (
              <tr
                key={item.forge_id}
                style={{ borderBottom: '1px solid var(--border)' }}
              >
                <td style={{ padding: '10px 12px', fontWeight: 600 }}>{item.character_name}</td>
                <td style={{ padding: '10px 12px' }}><ModeBadge mode={item.mode} /></td>
                <td style={{ padding: '10px 12px' }}><StageBadge stage={item.status} /></td>
                <td style={{ padding: '10px 12px' }}><StageBadge stage={item.stage} /></td>
                <td style={{ padding: '10px 12px', color: 'var(--text-muted)', fontSize: 12, whiteSpace: 'nowrap' }}>
                  {formatDateTime(item.started_at)}
                </td>
                <td style={{ padding: '10px 12px', color: 'var(--text-muted)', fontSize: 12, whiteSpace: 'nowrap' }}>
                  {item.finished_at ? formatDateTime(item.finished_at) : '—'}
                </td>
                <td style={{ padding: '10px 12px', color: 'var(--text-muted)', fontSize: 11, fontFamily: 'monospace' }}>
                  {item.resident_id ? item.resident_id.slice(0, 8) + '...' : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 16, justifyContent: 'center' }}>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              color: page <= 1 ? 'var(--text-muted)' : 'white',
              padding: '5px 12px',
              borderRadius: 5,
              fontSize: 13,
              cursor: page <= 1 ? 'default' : 'pointer',
            }}
          >
            上一页
          </button>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              color: page >= totalPages ? 'var(--text-muted)' : 'white',
              padding: '5px 12px',
              borderRadius: 5,
              fontSize: 13,
              cursor: page >= totalPages ? 'default' : 'pointer',
            }}
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}

// ─── ForgeMonitorPanel ────────────────────────────────────────────

interface ForgeMonitorPanelProps {
  token: string
}

export function ForgeMonitorPanel({ token }: ForgeMonitorPanelProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      {/* Active sessions */}
      <section>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>活跃会话</h3>
          <span style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: '#22c55e',
            boxShadow: '0 0 6px #22c55e',
            animation: 'pulse 2s infinite',
            display: 'inline-block',
          }} />
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>每 10 秒自动刷新</span>
        </div>
        <ActiveSessions token={token} />
      </section>

      <div style={{ borderTop: '1px solid var(--border)' }} />

      {/* History */}
      <section>
        <h3 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 14px' }}>历史记录</h3>
        <HistoryTable token={token} />
      </section>
    </div>
  )
}
