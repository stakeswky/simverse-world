import { useCallback, useEffect, useState } from 'react'
import {
  getAdminResidents,
  adminEditResident,
} from '../../services/api'
import type { AdminResident } from '../../services/api'

const DISTRICT_OPTIONS = [
  { value: '', label: '全部地点' },
  { value: 'academy', label: '学院' },
  { value: 'tavern', label: '酒馆' },
  { value: 'cafe', label: '咖啡馆' },
  { value: 'workshop', label: '工坊' },
  { value: 'library', label: '图书馆' },
  { value: 'shop', label: '杂货铺' },
  { value: 'town_hall', label: '市政厅' },
  { value: 'north_path', label: '北林荫道' },
  { value: 'central_plaza', label: '中央广场' },
  { value: 'south_lawn', label: '南草坪' },
  { value: 'town_entrance', label: '小镇入口' },
  { value: 'outdoor', label: '户外' },
]

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'idle', label: '空闲' },
  { value: 'chatting', label: '对话中' },
  { value: 'popular', label: '热门' },
  { value: 'sleeping', label: '沉睡' },
]

const STATUS_COLORS: Record<string, string> = {
  idle: '#22c55e',
  chatting: '#3b82f6',
  popular: '#f97316',
  sleeping: '#6b7280',
}

const STATUS_LABELS: Record<string, string> = {
  idle: '空闲',
  chatting: '对话中',
  popular: '热门',
  sleeping: '沉睡',
}

interface ExpandedRowProps {
  resident: AdminResident
  token: string
  onSaved: () => void
}

function ExpandedRow({ resident, token, onSaved }: ExpandedRowProps) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const handleSave = useCallback(async () => {
    setSaving(true)
    setError(null)
    try {
      await adminEditResident(token, resident.id, {
        name: resident.name,
        district: resident.district,
        status: resident.status,
      })
      setSuccess(true)
      setTimeout(() => { setSuccess(false); onSaved() }, 1000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }, [token, resident, onSaved])

  const preview = (text: string | null) =>
    text ? text.slice(0, 100) + (text.length > 100 ? '...' : '') : '(空)'

  return (
    <tr>
      <td
        colSpan={8}
        style={{
          padding: '12px 20px',
          background: '#0f0f12',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase' }}>
              Ability
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
              {preview(resident.ability_md)}
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase' }}>
              Persona
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
              {preview(resident.persona_md)}
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase' }}>
              Soul
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
              {preview(resident.soul_md)}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12 }}>
          <button
            onClick={handleSave}
            disabled={saving || success}
            style={{
              background: success ? '#22c55e' : 'var(--accent-red)',
              color: 'white',
              border: 'none',
              padding: '6px 16px',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: saving ? 'wait' : 'pointer',
              opacity: saving || success ? 0.8 : 1,
            }}
          >
            {saving ? '保存中...' : success ? '已保存' : '保存更改'}
          </button>
          {error && (
            <span style={{ fontSize: 12, color: '#e94560' }}>{error}</span>
          )}
        </div>
      </td>
    </tr>
  )
}

interface ResidentsPanelProps {
  token: string
}

export function ResidentsPanel({ token }: ResidentsPanelProps) {
  const [residents, setResidents] = useState<AdminResident[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [perPage] = useState(20)
  const [search, setSearch] = useState('')
  const [district, setDistrict] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const fetchResidents = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await getAdminResidents(token, {
        page,
        per_page: perPage,
        search: search || undefined,
        district: district || undefined,
        status: status || undefined,
      })
      setResidents(resp.items)
      setTotal(resp.total)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [token, page, perPage, search, district, status])

  useEffect(() => {
    void fetchResidents()
  }, [fetchResidents])

  const totalPages = Math.ceil(total / perPage)

  const inputStyle: React.CSSProperties = {
    padding: '7px 11px',
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    color: 'white',
    fontSize: 13,
    outline: 'none',
  }

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    cursor: 'pointer',
  }

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="搜索名称..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          style={{ ...inputStyle, width: 200 }}
        />
        <select
          value={district}
          onChange={(e) => { setDistrict(e.target.value); setPage(1) }}
          style={selectStyle}
        >
          {DISTRICT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1) }}
          style={selectStyle}
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>
          共 {total} 条
        </div>
      </div>

      {/* Error */}
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

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['名称', '类型', '地点', '评分', '热度', '状态', '创建者', '操作'].map((h) => (
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
                <td colSpan={8} style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
                  加载中...
                </td>
              </tr>
            ) : residents.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
                  暂无数据
                </td>
              </tr>
            ) : residents.flatMap((r) => {
              const isExpanded = expandedId === r.id
              const rows = [
                <tr
                  key={r.id}
                  style={{
                    borderBottom: isExpanded ? 'none' : '1px solid var(--border)',
                    cursor: 'pointer',
                    background: isExpanded ? '#0f0f12' : 'transparent',
                    transition: 'background 0.15s',
                  }}
                  onClick={() => setExpandedId(isExpanded ? null : r.id)}
                >
                  {/* Name + sprite */}
                  <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{
                        width: 28,
                        height: 28,
                        background: 'var(--bg-input)',
                        borderRadius: 6,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 14,
                        flexShrink: 0,
                      }}>
                        🧑
                      </div>
                      <span style={{ fontWeight: 600 }}>{r.name}</span>
                    </div>
                  </td>
                  {/* Type */}
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{
                      fontSize: 11,
                      padding: '2px 8px',
                      borderRadius: 4,
                      background: r.type === 'NPC' ? 'rgba(139,92,246,0.15)' : 'rgba(59,130,246,0.15)',
                      color: r.type === 'NPC' ? '#a78bfa' : '#60a5fa',
                      fontWeight: 600,
                    }}>
                      {r.type}
                    </span>
                  </td>
                  {/* District */}
                  <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>
                    {r.district}
                  </td>
                  {/* Star rating */}
                  <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                    {'★'.repeat(r.star_rating)}
                    {'☆'.repeat(Math.max(0, 5 - r.star_rating))}
                  </td>
                  {/* Heat */}
                  <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>
                    {r.heat}
                  </td>
                  {/* Status */}
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{
                      fontSize: 11,
                      padding: '2px 8px',
                      borderRadius: 4,
                      background: `${STATUS_COLORS[r.status] ?? '#6b7280'}22`,
                      color: STATUS_COLORS[r.status] ?? '#9ca3af',
                      fontWeight: 600,
                    }}>
                      {STATUS_LABELS[r.status] ?? r.status}
                    </span>
                  </td>
                  {/* Creator */}
                  <td style={{ padding: '10px 12px', color: 'var(--text-muted)', fontSize: 12 }}>
                    {r.creator ?? '—'}
                  </td>
                  {/* Actions */}
                  <td style={{ padding: '10px 12px' }} onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : r.id)}
                      style={{
                        background: 'var(--bg-input)',
                        border: '1px solid var(--border)',
                        color: 'var(--text-secondary)',
                        padding: '4px 12px',
                        borderRadius: 5,
                        fontSize: 12,
                        cursor: 'pointer',
                      }}
                    >
                      {isExpanded ? '收起' : '展开'}
                    </button>
                  </td>
                </tr>,
              ]
              if (isExpanded) {
                rows.push(
                  <ExpandedRow
                    key={`${r.id}-expanded`}
                    resident={r}
                    token={token}
                    onSaved={fetchResidents}
                  />,
                )
              }
              return rows
            })}
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
