import { useEffect, useState, useCallback } from 'react'
import { useGameStore } from '../../stores/gameStore'
import {
  getAdminDashboardStats,
  getAdminDashboardHealth,
  type AdminDashboardStats,
  type AdminDashboardHealth,
} from '../../services/api'

interface MetricCardProps {
  icon: string
  label: string
  value: string | number
  color?: string
}

function MetricCard({ icon, label, value, color }: MetricCardProps) {
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 12,
      padding: '20px 24px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      flex: 1,
      minWidth: 160,
    }}>
      <div style={{ fontSize: 24 }}>{icon}</div>
      <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{label}</div>
      <div style={{
        fontSize: 28,
        fontWeight: 700,
        color: color ?? 'var(--text-primary)',
      }}>
        {value}
      </div>
    </div>
  )
}

function HealthDot({ status }: { status: 'ok' | 'error' | 'loading' }) {
  const color = status === 'ok' ? '#22c55e' : status === 'error' ? '#ef4444' : '#6b7280'
  return (
    <span style={{
      display: 'inline-block',
      width: 10,
      height: 10,
      borderRadius: '50%',
      background: color,
      boxShadow: status === 'ok' ? `0 0 6px ${color}` : undefined,
      flexShrink: 0,
    }} />
  )
}

export function DashboardPanel() {
  const token = useGameStore((s) => s.token)
  const [stats, setStats] = useState<AdminDashboardStats | null>(null)
  const [health, setHealth] = useState<AdminDashboardHealth | null>(null)
  const [statsError, setStatsError] = useState<string | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const fetchData = useCallback(async () => {
    if (!token) return

    setStatsError(null)
    setHealthError(null)

    await Promise.allSettled([
      getAdminDashboardStats(token)
        .then(setStats)
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : 'Failed to load stats'
          setStatsError(msg)
        }),
      getAdminDashboardHealth(token)
        .then(setHealth)
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : 'Failed to load health'
          setHealthError(msg)
        }),
    ])

    setLastRefresh(new Date())
  }, [token])

  useEffect(() => {
    void fetchData()
    const interval = setInterval(() => { void fetchData() }, 30_000)
    return () => clearInterval(interval)
  }, [fetchData])

  const formatTime = (d: Date) =>
    d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>📊 仪表盘</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            上次刷新：{formatTime(lastRefresh)}
          </span>
          <button
            onClick={() => { void fetchData() }}
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '5px 12px',
              fontSize: 12,
              cursor: 'pointer',
              color: 'var(--text-secondary)',
            }}
          >
            ↻ 刷新
          </button>
        </div>
      </div>

      {/* Metric cards */}
      <div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12, fontWeight: 600 }}>
          实时指标
        </div>
        {statsError && (
          <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 12, padding: '8px 12px', background: '#ef444415', borderRadius: 6 }}>
            ⚠️ {statsError}
          </div>
        )}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <MetricCard
            icon="🟢"
            label="在线用户"
            value={stats?.online_users ?? '—'}
            color="var(--accent-green)"
          />
          <MetricCard
            icon="📝"
            label="今日注册"
            value={stats?.today_registrations ?? '—'}
          />
          <MetricCard
            icon="💬"
            label="活跃对话"
            value={stats?.active_chats ?? '—'}
            color="#a78bfa"
          />
          <MetricCard
            icon="🪙"
            label="SC 净流量"
            value={stats?.soul_coin_net_flow != null
              ? (stats.soul_coin_net_flow >= 0 ? `+${stats.soul_coin_net_flow}` : `${stats.soul_coin_net_flow}`)
              : '—'}
            color={stats?.soul_coin_net_flow != null
              ? (stats.soul_coin_net_flow >= 0 ? 'var(--accent-green)' : '#ef4444')
              : 'var(--text-primary)'}
          />
        </div>
      </div>

      {/* Health status */}
      <div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12, fontWeight: 600 }}>
          服务健康状态
        </div>
        {healthError && (
          <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 12, padding: '8px 12px', background: '#ef444415', borderRadius: 6 }}>
            ⚠️ {healthError}
          </div>
        )}
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 12,
          padding: '16px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          maxWidth: 360,
        }}>
          {[
            { key: 'searxng' as const, label: 'SearXNG', icon: '🔍' },
            { key: 'llm_api' as const, label: 'LLM API', icon: '🤖' },
          ].map(({ key, label, icon }) => {
            const status = health ? health[key] : 'loading'
            return (
              <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
                  <span>{icon}</span>
                  <span>{label}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <HealthDot status={status === 'loading' ? 'loading' : status} />
                  <span style={{
                    fontSize: 12,
                    color: status === 'ok' ? '#22c55e' : status === 'error' ? '#ef4444' : 'var(--text-muted)',
                    fontWeight: 600,
                  }}>
                    {status === 'loading' ? '检查中…' : status === 'ok' ? '正常' : '异常'}
                  </span>
                  {status === 'error' && health?.details?.[key] && (
                    <span style={{ fontSize: 11, color: '#ef4444', opacity: 0.8, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={health.details[key] ?? ''}>
                      {health.details[key]}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Auto-refresh notice */}
      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
        每 30 秒自动刷新
      </div>
    </div>
  )
}
