import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getAdminLivingLoopMetrics = vi.hoisted(() => vi.fn())

vi.mock('../../services/api', () => ({
  getAdminLivingLoopMetrics,
}))

import { LivingLoopFunnelPanel } from './LivingLoopFunnelPanel'

const metrics = {
  window: {
    from: '2026-08-01T00:00:00Z',
    to: '2026-08-28T23:59:59Z',
  },
  generated_at: '2026-08-28T12:00:00Z',
  today_unique_users: 120,
  decision_viewed_unique_users: 100,
  choice_confirmed_unique_users: 75,
  choice_completion_rate: 0.75,
  settled_result_count: 60,
  delayed_result_viewed_unique_users: 30,
  return_within_48h_rate: 0.5,
  median_choice_seconds: 92,
  choice_distribution: [
    { choice_key: 'public_support', count: 20, share: 20 / 75 },
    { choice_key: 'private_mediation', count: 35, share: 35 / 75 },
    { choice_key: 'collect_evidence', count: 20, share: 20 / 75 },
  ],
}

beforeEach(() => {
  getAdminLivingLoopMetrics.mockReset().mockResolvedValue(metrics)
})

afterEach(cleanup)

function metricCard(label: string): HTMLElement {
  const labelNode = screen.getByText(label)
  const card = labelNode.closest('[data-metric]')
  expect(card).not.toBeNull()
  return card as HTMLElement
}

describe('LivingLoopFunnelPanel', () => {
  it('renders the complete read-only P0 funnel and all three option distributions', async () => {
    render(<LivingLoopFunnelPanel token="admin-token" />)

    expect(screen.getByRole('status', { name: '正在加载 Living Loop P0 漏斗' })).toBeInTheDocument()
    const panel = await screen.findByRole('region', { name: 'Living Loop P0 漏斗' })
    expect(getAdminLivingLoopMetrics).toHaveBeenCalledWith('admin-token')
    expect(within(panel).getByText(/2026-08-01/)).toBeInTheDocument()
    expect(metricCard('独立 Today 用户')).toHaveTextContent('120')
    expect(metricCard('独立决策查看用户')).toHaveTextContent('100')
    expect(metricCard('确认选择用户')).toHaveTextContent('75')
    expect(metricCard('选择完成率')).toHaveTextContent('75.0%')
    expect(metricCard('到期结果')).toHaveTextContent('60')
    expect(metricCard('延迟结果查看用户')).toHaveTextContent('30')
    expect(metricCard('48 小时回访率')).toHaveTextContent('50.0%')
    expect(metricCard('中位决策时间')).toHaveTextContent('1 分 32 秒')

    const distribution = within(panel).getByRole('list', { name: '三个选项的选择分布' })
    expect(within(distribution).getByText('公开站出来支持工人')).toBeInTheDocument()
    expect(within(distribution).getByText('先组织一场私下调解')).toBeInTheDocument()
    expect(within(distribution).getByText('先核实排班和欠薪证据')).toBeInTheDocument()
    expect(within(distribution).getByText('35 次')).toBeInTheDocument()
    expect(within(distribution).getByText('46.7%')).toBeInTheDocument()
    expect(JSON.stringify(metrics)).not.toContain('email')
    expect(JSON.stringify(metrics)).not.toContain('user_id')
  })

  it('keeps an endpoint failure local to the card and retries without affecting AdminPage', async () => {
    getAdminLivingLoopMetrics
      .mockRejectedValueOnce(new Error('metrics unavailable'))
      .mockResolvedValueOnce(metrics)

    render(<LivingLoopFunnelPanel token="admin-token" />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Living Loop 漏斗暂时不可用')
    fireEvent.click(screen.getByRole('button', { name: '重试漏斗数据' }))

    expect(await screen.findByRole('region', { name: 'Living Loop P0 漏斗' })).toBeInTheDocument()
    expect(getAdminLivingLoopMetrics).toHaveBeenCalledTimes(2)
  })

  it('renders unavailable derived rates as an em dash instead of inventing zeroes', async () => {
    getAdminLivingLoopMetrics.mockResolvedValue({
      ...metrics,
      choice_completion_rate: null,
      return_within_48h_rate: null,
      median_choice_seconds: null,
    })

    render(<LivingLoopFunnelPanel token="admin-token" />)
    await screen.findByRole('region', { name: 'Living Loop P0 漏斗' })

    expect(metricCard('选择完成率')).toHaveTextContent('—')
    expect(metricCard('48 小时回访率')).toHaveTextContent('—')
    expect(metricCard('中位决策时间')).toHaveTextContent('—')
  })
})
