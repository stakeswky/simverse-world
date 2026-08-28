import '@testing-library/jest-dom/vitest'
import { act, cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { VerificationResult } from '../../services/api/challenge'
import { OutcomeComparison } from './OutcomeComparison'

function verificationResult(): VerificationResult {
  const baseline = {
    high_food_risk_residents: 2,
    social_tension: 68,
    strike_risk_pct: 74,
    stabilized_residents: 0,
  }
  const actual = {
    high_food_risk_residents: 1,
    social_tension: 54,
    strike_risk_pct: 38,
    stabilized_residents: 5,
  }
  return {
    receipt_id: 'SV-2042-A1B2C3D4',
    advance_hours: 72,
    baseline_snapshot: {
      tick_index: 0,
      elapsed_hours: 0,
      world_time: '2042-06-12T08:00:00Z',
      metrics: baseline,
      external_event_ids: [],
    },
    tick_snapshots: Array.from({ length: 12 }, (_, index) => ({
      tick_index: index + 1,
      elapsed_hours: (index + 1) * 6,
      world_time: new Date(
        Date.parse('2042-06-12T08:00:00Z') + (index + 1) * 6 * 3_600_000,
      ).toISOString(),
      metrics: index === 11 ? actual : baseline,
      external_event_ids: [`harbor-market-shift-${index + 1}`],
    })),
    forecast: {
      seeds: [101, 102, 103, 104, 105],
      high_food_risk_residents: { min: 0, max: 1 },
      social_tension: { min: 50, max: 58 },
      strike_risk_pct: { min: 28, max: 42 },
      stabilized_residents: { min: 5, max: 6 },
    },
    actual,
    no_action: {
      high_food_risk_residents: 3,
      social_tension: 81,
      strike_risk_pct: 100,
      stabilized_residents: 0,
      strike_event_triggered: true,
    },
    notable_deviation: 'Escrow miss caused a notable deviation.',
  }
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('OutcomeComparison', () => {
  it('renders three complete result columns and all 13 readable time points', () => {
    render(<OutcomeComparison verification={verificationResult()} />)

    const prediction = screen.getByRole('article', { name: 'Prediction' })
    const actual = screen.getByRole('article', { name: 'Actual after 72h' })
    const control = screen.getByRole('article', { name: 'No-action control' })
    for (const column of [prediction, actual, control]) {
      expect(within(column).getByText('High food risk')).toBeInTheDocument()
      expect(within(column).getByText('Social tension')).toBeInTheDocument()
      expect(within(column).getByText('Strike risk')).toBeInTheDocument()
      expect(within(column).getByText('Stabilized')).toBeInTheDocument()
    }
    expect(within(prediction).getByText('0–1')).toBeInTheDocument()
    expect(within(actual).getByText('54')).toBeInTheDocument()
    expect(within(control).getByText('100%')).toBeInTheDocument()
    expect(within(control).getByText('Strike triggered')).toBeInTheDocument()

    const points = screen.getAllByTestId('outcome-timeline-point')
    expect(points).toHaveLength(13)
    expect(points[0]).toHaveTextContent('T+0 baseline')
    expect(points[1]).toHaveTextContent('T+6h')
    expect(points[12]).toHaveTextContent('T+72h')
    expect(screen.getByText('Escrow miss caused a notable deviation.')).toBeInTheDocument()
  })

  it('animates only the local timeline highlight and cleans up without changing final data', () => {
    vi.useFakeTimers()
    const verification = verificationResult()
    const finalBefore = structuredClone(verification.actual)
    const view = render(
      <OutcomeComparison verification={verification} animationIntervalMs={300} />,
    )

    const points = screen.getAllByTestId('outcome-timeline-point')
    expect(points[0]).toHaveAttribute('data-active', 'true')
    expect(screen.getByRole('article', { name: 'Actual after 72h' })).toHaveTextContent('54')
    act(() => vi.advanceTimersByTime(300))
    expect(points[1]).toHaveAttribute('data-active', 'true')
    expect(verification.actual).toEqual(finalBefore)

    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
    expect(verification.actual).toEqual(finalBefore)
  })
})
