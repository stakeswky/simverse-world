import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getAdminDashboardHealth,
  getAdminDashboardStats,
  getAdminDashboardTrends,
  getAdminEconomySeries,
  getAdminEconomyStats,
  getAdminLlmUsageSummary,
  type AdminDashboardHealth,
  type AdminDashboardStats,
  type AdminDashboardTrend,
  type EconomySeriesPoint,
  type AdminEconomyStats,
  type LlmUsageSummary,
} from '../../services/api'
import { LivingLoopFunnelPanel } from './LivingLoopFunnelPanel'

interface DashboardPanelProps {
  token: string
}

interface MetricCardProps {
  label: string
  value: string | number
  note: string
  color: string
  glow: string
}

function MetricCard({ label, value, note, color, glow }: MetricCardProps) {
  return (
    <div className="admin-metric-card" style={{ '--metric-glow': glow } as React.CSSProperties}>
      <div className="admin-metric-card__label">{label}</div>
      <div className="admin-metric-card__value" style={{ color }}>{value}</div>
      <div className="admin-metric-card__note">{note}</div>
    </div>
  )
}

function points(values: number[], width: number, height: number) {
  if (values.length === 0) return ''
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const span = Math.max(max - min, 1)
  return values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width
    const y = height - ((value - min) / span) * (height - 16) - 8
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

function TrendChart({
  trends,
  economySeries,
}: {
  trends: AdminDashboardTrend[]
  economySeries: EconomySeriesPoint[]
}) {
  const width = 720
  const height = 210
  const registrations = points(trends.map((item) => item.users), width, height)
  const conversations = points(trends.map((item) => item.conversations), width, height)
  const consumedByDate = new Map(economySeries.map((item) => [item.date, item.consumed]))
  const spend = points(trends.map((item) => consumedByDate.get(item.date) ?? 0), width, height)
  const firstDate = trends.at(0)?.date
  const lastDate = trends.at(-1)?.date

  if (trends.length === 0) return <div className="admin-empty">还没有足够的趋势数据</div>

  return (
    <>
      <svg className="admin-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="小镇活跃、注册与灵魂币消耗趋势">
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line key={ratio} className="admin-chart-grid" x1="0" y1={height * ratio} x2={width} y2={height * ratio} />
        ))}
        <polyline className="admin-chart-line" points={conversations} stroke="#0071e3" />
        <polyline className="admin-chart-line" points={registrations} stroke="#34c759" />
        <polyline className="admin-chart-line" points={spend} stroke="#af52de" opacity="0.8" />
      </svg>
      <div className="admin-chart-legend">
        <span><i style={{ background: '#0071e3' }} />居民对话</span>
        <span><i style={{ background: '#34c759' }} />新增居民</span>
        <span><i style={{ background: '#af52de' }} />SC 消耗</span>
        <span style={{ marginLeft: 'auto' }}>{firstDate} — {lastDate}</span>
      </div>
    </>
  )
}

function HealthList({ health }: { health: AdminDashboardHealth | null }) {
  const rows = [
    { key: 'searxng' as const, label: '世界检索', detail: 'SearXNG' },
    { key: 'llm_api' as const, label: '居民思考', detail: 'LLM API' },
  ]

  return (
    <div className="admin-status-list">
      {rows.map((row) => {
        const status = health?.[row.key]
        const ok = status === 'ok'
        return (
          <div key={row.key} className="admin-status-row">
            <span className="admin-live-dot" style={{ background: ok ? '#34c759' : '#ff3b30' }} />
            <div className="admin-status-row__copy">
              <div className="admin-status-row__label">{row.label}</div>
              <div className="admin-status-row__detail">
                {health?.details?.[row.key] || row.detail}
              </div>
            </div>
            <span className="admin-status-row__value" style={{ color: ok ? '#248a3d' : '#d70015' }}>
              {health ? (ok ? '正常' : status === 'timeout' ? '超时' : '异常') : '检查中'}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export function DashboardPanel({ token }: DashboardPanelProps) {
  const [stats, setStats] = useState<AdminDashboardStats | null>(null)
  const [trends, setTrends] = useState<AdminDashboardTrend[]>([])
  const [economySeries, setEconomySeries] = useState<EconomySeriesPoint[]>([])
  const [health, setHealth] = useState<AdminDashboardHealth | null>(null)
  const [economy, setEconomy] = useState<AdminEconomyStats | null>(null)
  const [llm, setLlm] = useState<LlmUsageSummary | null>(null)
  const [failedSources, setFailedSources] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    const results = await Promise.allSettled([
      getAdminDashboardStats(token),
      getAdminDashboardTrends(token),
      getAdminEconomySeries(token, 7),
      getAdminDashboardHealth(token),
      getAdminEconomyStats(token),
      getAdminLlmUsageSummary(token, 24),
    ])
    const sourceNames = ['总览', '发展趋势', '经济趋势', '运行状态', '经济统计', '模型用量']
    if (results[0].status === 'fulfilled') setStats(results[0].value)
    if (results[1].status === 'fulfilled') setTrends(results[1].value)
    if (results[2].status === 'fulfilled') setEconomySeries(results[2].value.series)
    if (results[3].status === 'fulfilled') setHealth(results[3].value)
    if (results[4].status === 'fulfilled') setEconomy(results[4].value)
    if (results[5].status === 'fulfilled') setLlm(results[5].value)
    setFailedSources(results.flatMap((result, index) => result.status === 'rejected' ? [sourceNames[index]] : []))
    setLastRefresh(new Date())
    setLoading(false)
  }, [token])

  useEffect(() => {
    const initial = setTimeout(() => { void load() }, 0)
    const interval = setInterval(() => { void load() }, 30_000)
    return () => {
      clearTimeout(initial)
      clearInterval(interval)
    }
  }, [load])

  const netFlow = stats?.soul_coin_net_flow
  const economySignal = useMemo(() => {
    if (!economy || economy.total_issued === 0) return '等待形成流通'
    const ratio = economy.total_consumed / economy.total_issued
    if (ratio >= 0.8) return '消耗充分'
    if (ratio >= 0.45) return '流通平稳'
    return '留存偏高'
  }, [economy])

  return (
    <div className="admin-analytics-stack">
      <div className="admin-section-heading">
        <div>
          <h2>此刻的小镇</h2>
          <p>关注变化方向，而不是逐项管理系统参数。</p>
        </div>
        <button type="button" className="admin-ghost-button" onClick={() => { void load() }}>
          {loading ? '正在同步…' : lastRefresh ? `更新于 ${lastRefresh.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}` : '刷新数据'}
        </button>
      </div>

      {failedSources.length > 0 && (
        <div className="admin-error">
          {failedSources.join('、')}暂时不可用，已保留其他实时数据。
        </div>
      )}

      <div className="admin-metric-grid">
        <MetricCard
          label="在线人口"
          value={stats?.online_users ?? '—'}
          note={`今日新增 ${stats?.today_registrations ?? '—'} 人`}
          color="#0071e3"
          glow="rgba(0, 113, 227, 0.08)"
        />
        <MetricCard
          label="社会互动"
          value={stats?.active_chats ?? '—'}
          note="当前活跃对话"
          color="#34c759"
          glow="rgba(52, 199, 89, 0.08)"
        />
        <MetricCard
          label="SOUL COIN 净流量"
          value={netFlow == null ? '—' : `${netFlow >= 0 ? '+' : ''}${netFlow}`}
          note={economySignal}
          color={netFlow != null && netFlow < 0 ? '#ff3b30' : '#af52de'}
          glow="rgba(175, 82, 222, 0.08)"
        />
        <MetricCard
          label="24H AI 成本"
          value={llm ? `$${llm.total.est_cost_usd.toFixed(2)}` : '—'}
          note={llm ? `${llm.total.calls} 次调用` : '正在统计'}
          color="#ff9f0a"
          glow="rgba(255, 159, 10, 0.08)"
        />
      </div>

      <div className="admin-analytics-grid">
        <section className="admin-analytics-card">
          <div className="admin-card-title">
            <h3>发展趋势</h3>
            <span>新增 / 对话 / 消耗</span>
          </div>
          <TrendChart trends={trends} economySeries={economySeries} />
        </section>

        <section className="admin-analytics-card">
          <div className="admin-card-title">
            <h3>运行信号</h3>
            <span>实时</span>
          </div>
          <HealthList health={health} />
          <div className="admin-distribution" style={{ marginTop: 12 }}>
            <div className="admin-distribution__item">
              <div className="admin-distribution__value">{economy?.total_users ?? '—'}</div>
              <div className="admin-distribution__label">经济参与者</div>
            </div>
            <div className="admin-distribution__item">
              <div className="admin-distribution__value">{economy ? economy.avg_balance.toFixed(1) : '—'}</div>
              <div className="admin-distribution__label">人均 SC 余额</div>
            </div>
          </div>
        </section>
      </div>

      <LivingLoopFunnelPanel token={token} />
    </div>
  )
}
