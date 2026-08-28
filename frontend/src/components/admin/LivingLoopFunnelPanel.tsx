import { useCallback, useEffect, useState } from 'react'
import {
  getAdminLivingLoopMetrics,
  type AdminLivingLoopMetrics,
  type LivingLoopChoiceKey,
} from '../../services/api'

const CHOICE_LABELS: Record<LivingLoopChoiceKey, string> = {
  public_support: '公开站出来支持工人',
  private_mediation: '先组织一场私下调解',
  collect_evidence: '先核实排班和欠薪证据',
}

function percentage(value: number | null): string {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function duration(value: number | null): string {
  if (value == null) return '—'
  const totalSeconds = Math.max(0, Math.round(value))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds} 秒`
  return `${minutes} 分 ${seconds} 秒`
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="living-loop-funnel__metric" data-metric>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export function LivingLoopFunnelPanel({ token }: { token: string }) {
  const [metrics, setMetrics] = useState<AdminLivingLoopMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      setMetrics(await getAdminLivingLoopMetrics(token))
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  if (loading && !metrics) {
    return (
      <section className="admin-analytics-card living-loop-funnel living-loop-funnel--state">
        <div role="status" aria-label="正在加载 Living Loop P0 漏斗">正在加载 Living Loop P0 漏斗…</div>
      </section>
    )
  }

  if (error && !metrics) {
    return (
      <section className="admin-analytics-card living-loop-funnel living-loop-funnel--state">
        <div role="alert">Living Loop 漏斗暂时不可用</div>
        <button type="button" className="admin-ghost-button" onClick={() => { void load() }}>
          重试漏斗数据
        </button>
      </section>
    )
  }

  if (!metrics) return null

  return (
    <section className="admin-analytics-card living-loop-funnel" role="region" aria-label="Living Loop P0 漏斗">
      <div className="admin-card-title">
        <div>
          <p className="living-loop-funnel__eyebrow">LIVING LOOP P0</p>
          <h3>回访与选择漏斗</h3>
        </div>
        <span>{metrics.window.from.slice(0, 10)} — {metrics.window.to.slice(0, 10)}</span>
      </div>

      <div className="living-loop-funnel__metrics">
        <Metric label="独立 Today 用户" value={metrics.today_unique_users} />
        <Metric label="独立决策查看用户" value={metrics.decision_viewed_unique_users} />
        <Metric label="确认选择用户" value={metrics.choice_confirmed_unique_users} />
        <Metric label="选择完成率" value={percentage(metrics.choice_completion_rate)} />
        <Metric label="到期结果" value={metrics.settled_result_count} />
        <Metric label="延迟结果查看用户" value={metrics.delayed_result_viewed_unique_users} />
        <Metric label="48 小时回访率" value={percentage(metrics.return_within_48h_rate)} />
        <Metric label="中位决策时间" value={duration(metrics.median_choice_seconds)} />
      </div>

      <div className="living-loop-funnel__distribution">
        <h4>三个选项的选择分布</h4>
        <ul aria-label="三个选项的选择分布">
          {metrics.choice_distribution.map((item) => (
            <li key={item.choice_key}>
              <div>
                <span>{CHOICE_LABELS[item.choice_key]}</span>
                <strong>{item.count} 次</strong>
              </div>
              <div className="living-loop-funnel__bar" aria-hidden="true">
                <span style={{ width: `${Math.max(0, Math.min(100, item.share * 100))}%` }} />
              </div>
              <span>{(item.share * 100).toFixed(1)}%</span>
            </li>
          ))}
        </ul>
      </div>

      <p className="living-loop-funnel__generated">
        聚合生成时间：{new Date(metrics.generated_at).toLocaleString('zh-CN', { timeZone: 'UTC' })} UTC
      </p>
    </section>
  )
}
