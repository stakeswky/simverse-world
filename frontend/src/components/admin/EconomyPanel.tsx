import { useEffect, useState } from 'react'
import {
  getAdminEconomyStats,
  getAdminTransactions,
  getAdminEconomyConfig,
  updateAdminEconomyConfig,
  type AdminEconomyStats,
  type AdminTransaction,
  type AdminEconomyConfig,
} from '../../services/api'

// ─── Shared sub-components ────────────────────────────────────────

function SectionHeader({ icon, title }: { icon: string; title: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      marginBottom: 20, paddingBottom: 12,
      borderBottom: '1px solid var(--border)',
    }}>
      <span style={{ fontSize: 18 }}>{icon}</span>
      <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>{title}</h2>
    </div>
  )
}

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '20px 24px', marginBottom: 16,
    }}>
      {children}
    </div>
  )
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 500 }}>
      {children}
    </div>
  )
}

function SaveButton({ onClick, saving, saved }: { onClick: () => void; saving: boolean; saved: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={saving}
      style={{
        marginTop: 12, padding: '7px 20px',
        background: saved ? '#53d769' : 'var(--accent)',
        color: 'white', border: 'none', borderRadius: 6,
        fontSize: 13, fontWeight: 600, cursor: saving ? 'default' : 'pointer',
        transition: 'background 0.2s ease', opacity: saving ? 0.7 : 1,
      }}
    >
      {saving ? '保存中...' : saved ? '已保存 ✓' : '保存'}
    </button>
  )
}

// ─── Stat Cards ──────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: number | null
  color?: string
}

function StatCard({ label, value, color }: StatCardProps) {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '16px 20px',
      display: 'flex', flexDirection: 'column', gap: 6, flex: '1 1 160px',
    }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color ?? 'var(--text-primary)' }}>
        {value !== null ? value.toLocaleString() : '—'}
      </div>
    </div>
  )
}

// ─── Stats Section ───────────────────────────────────────────────

function EconomyStatsSection({ token }: { token: string }) {
  const [stats, setStats] = useState<AdminEconomyStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await getAdminEconomyStats(token)
        setStats(data)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [token])

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: '12px 0', fontSize: 13 }}>加载统计数据...</div>
  }

  if (error || !stats) {
    return <div style={{ color: '#ff6b6b', padding: '12px 0', fontSize: 13 }}>{error ?? '加载失败'}</div>
  }

  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
      <StatCard label="总发行量" value={stats.total_issued} color="var(--accent)" />
      <StatCard label="总消耗量" value={stats.total_consumed} color="#ff6b6b" />
      <StatCard label="净流通量" value={stats.net_circulation} color="#53d769" />
      <StatCard label="用户总数" value={stats.total_users} />
      <StatCard label="用户平均余额" value={stats.avg_balance} />
    </div>
  )
}

// ─── Transaction Log ─────────────────────────────────────────────

const REASON_OPTIONS = [
  { value: '', label: '全部原因' },
  { value: 'signup_bonus', label: '注册奖励' },
  { value: 'daily_reward', label: '每日奖励' },
  { value: 'chat_cost', label: '对话消耗' },
  { value: 'creator_reward', label: '创作奖励' },
  { value: 'rating_bonus', label: '评分奖励' },
]

function TransactionLogSection({ token }: { token: string }) {
  const [items, setItems] = useState<AdminTransaction[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [reasonFilter, setReasonFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const perPage = 20

  useEffect(() => {
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await getAdminTransactions(token, {
          page,
          per_page: perPage,
          reason: reasonFilter || undefined,
        })
        setItems(data.items)
        setTotal(data.total)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [token, page, reasonFilter])

  const totalPages = Math.max(1, Math.ceil(total / perPage))

  const handleReasonChange = (value: string) => {
    setReasonFilter(value)
    setPage(1)
  }

  return (
    <SectionCard>
      <SectionHeader icon="📋" title="交易流水" />

      {/* Filters */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <FieldLabel>原因筛选</FieldLabel>
        <select
          value={reasonFilter}
          onChange={(e) => handleReasonChange(e.target.value)}
          style={{
            padding: '6px 10px',
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            borderRadius: 6, color: 'var(--text-primary)', fontSize: 13,
            outline: 'none', cursor: 'pointer',
          }}
        >
          {REASON_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>
          共 {total.toLocaleString()} 条记录
        </span>
      </div>

      {/* Table */}
      {error ? (
        <div style={{ color: '#ff6b6b', fontSize: 13, padding: '12px 0' }}>{error}</div>
      ) : loading ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '12px 0' }}>加载中...</div>
      ) : items.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '24px 0' }}>暂无记录</div>
      ) : (
        <>
          {/* Header row */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 80px 160px 150px',
            gap: 8,
            padding: '6px 12px',
            fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
            textTransform: 'uppercase', letterSpacing: '0.04em',
          }}>
            <span>原因</span>
            <span style={{ textAlign: 'right' }}>金额</span>
            <span>用户 ID</span>
            <span style={{ textAlign: 'right' }}>时间</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {items.map((tx) => (
              <div
                key={tx.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 80px 160px 150px',
                  gap: 8,
                  padding: '8px 12px',
                  background: 'var(--bg-input)',
                  borderRadius: 6,
                  border: '1px solid var(--border)',
                  alignItems: 'center',
                }}
              >
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{tx.reason}</span>
                <span style={{
                  fontSize: 13, fontWeight: 600, textAlign: 'right',
                  color: tx.amount > 0 ? '#53d769' : '#ff6b6b',
                }}>
                  {tx.amount > 0 ? '+' : ''}{tx.amount}
                </span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {tx.user_id}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'right' }}>
                  {new Date(tx.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, marginTop: 16 }}>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                style={{
                  padding: '5px 14px', borderRadius: 6, fontSize: 13,
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  color: page <= 1 ? 'var(--text-muted)' : 'var(--text-primary)',
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
                  padding: '5px 14px', borderRadius: 6, fontSize: 13,
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  color: page >= totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
                  cursor: page >= totalPages ? 'default' : 'pointer',
                }}
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}
    </SectionCard>
  )
}

// ─── Economy Config Form ─────────────────────────────────────────

interface NumberFieldProps {
  label: string
  value: string
  onChange: (v: string) => void
  hint?: string
}

function NumberField({ label, value, onChange, hint }: NumberFieldProps) {
  return (
    <div style={{ marginBottom: 14 }}>
      <FieldLabel>{label}</FieldLabel>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        min={0}
        step="any"
        style={{
          width: 160, padding: '8px 12px',
          background: 'var(--bg-input)', border: '1px solid var(--border)',
          borderRadius: 6, color: 'var(--text-primary)', fontSize: 13,
          outline: 'none', boxSizing: 'border-box',
        }}
      />
      {hint && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{hint}</div>
      )}
    </div>
  )
}

function EconomyConfigSection({ token }: { token: string }) {
  const [config, setConfig] = useState<AdminEconomyConfig | null>(null)
  const [signupBonus, setSignupBonus] = useState('')
  const [dailyReward, setDailyReward] = useState('')
  const [chatCost, setChatCost] = useState('')
  const [creatorReward, setCreatorReward] = useState('')
  const [ratingBonus, setRatingBonus] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await getAdminEconomyConfig(token)
        setConfig(data)
        setSignupBonus(String(data.signup_bonus))
        setDailyReward(String(data.daily_reward))
        setChatCost(String(data.chat_cost_per_turn))
        setCreatorReward(String(data.creator_reward))
        setRatingBonus(String(data.rating_bonus))
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [token])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      await updateAdminEconomyConfig(token, {
        signup_bonus: parseFloat(signupBonus),
        daily_reward: parseFloat(dailyReward),
        chat_cost_per_turn: parseFloat(chatCost),
        creator_reward: parseFloat(creatorReward),
        rating_bonus: parseFloat(ratingBonus),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <SectionCard>
      <SectionHeader icon="⚙️" title="经济参数配置" />

      {loading ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>加载配置...</div>
      ) : !config && error ? (
        <div style={{ color: '#ff6b6b', fontSize: 13 }}>{error}</div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0 24px' }}>
            <NumberField
              label="注册奖励 (signup_bonus)"
              value={signupBonus}
              onChange={setSignupBonus}
              hint="新用户注册时发放的灵魂币数量"
            />
            <NumberField
              label="每日奖励 (daily_reward)"
              value={dailyReward}
              onChange={setDailyReward}
              hint="每日签到奖励的灵魂币数量"
            />
            <NumberField
              label="每轮对话消耗 (chat_cost_per_turn)"
              value={chatCost}
              onChange={setChatCost}
              hint="每次对话轮次扣除的灵魂币"
            />
            <NumberField
              label="创作奖励 (creator_reward)"
              value={creatorReward}
              onChange={setCreatorReward}
              hint="角色被对话时，创作者获得的奖励"
            />
            <NumberField
              label="评分奖励 (rating_bonus)"
              value={ratingBonus}
              onChange={setRatingBonus}
              hint="角色获得评分时，创作者获得的奖励"
            />
          </div>

          {error && (
            <div style={{ color: '#ff6b6b', fontSize: 13, marginTop: 8 }}>{error}</div>
          )}

          <SaveButton onClick={() => void handleSave()} saving={saving} saved={saved} />
        </>
      )}
    </SectionCard>
  )
}

// ─── Main EconomyPanel ────────────────────────────────────────────

interface EconomyPanelProps {
  token: string
}

export function EconomyPanel({ token }: EconomyPanelProps) {
  return (
    <div style={{ maxWidth: 900 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 24, color: 'var(--text-primary)' }}>
        经济管理
      </h1>

      {/* Stat Cards */}
      <EconomyStatsSection token={token} />

      {/* Transaction Log */}
      <TransactionLogSection token={token} />

      {/* Economy Config */}
      <EconomyConfigSection token={token} />
    </div>
  )
}
