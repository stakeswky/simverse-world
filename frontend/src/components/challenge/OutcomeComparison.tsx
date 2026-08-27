import { useEffect, useMemo, useState } from 'react'

import type { VerificationResult } from '../../services/api/challenge'

interface OutcomeComparisonProps {
  verification: VerificationResult
  animationIntervalMs?: number
}

interface DisplayMetrics {
  highFoodRisk: string
  socialTension: string
  strikeRisk: string
  stabilized: string
}

function MetricList({ metrics }: { metrics: DisplayMetrics }) {
  return (
    <dl>
      <div><dt>High food risk</dt><dd>{metrics.highFoodRisk}</dd></div>
      <div><dt>Social tension</dt><dd>{metrics.socialTension}</dd></div>
      <div><dt>Strike risk</dt><dd>{metrics.strikeRisk}</dd></div>
      <div><dt>Stabilized</dt><dd>{metrics.stabilized}</dd></div>
    </dl>
  )
}

export function OutcomeComparison({
  verification,
  animationIntervalMs = 300,
}: OutcomeComparisonProps) {
  const timeline = useMemo(
    () => [verification.baseline_snapshot, ...verification.tick_snapshots],
    [verification.baseline_snapshot, verification.tick_snapshots],
  )
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    if (animationIntervalMs <= 0 || timeline.length < 2) return
    const interval = globalThis.setInterval(() => {
      setActiveIndex((current) => {
        if (current >= timeline.length - 1) {
          globalThis.clearInterval(interval)
          return current
        }
        return current + 1
      })
    }, animationIntervalMs)
    return () => globalThis.clearInterval(interval)
  }, [animationIntervalMs, timeline.length])

  const prediction: DisplayMetrics = {
    highFoodRisk: `${verification.forecast.high_food_risk_residents.min}–${verification.forecast.high_food_risk_residents.max}`,
    socialTension: `${verification.forecast.social_tension.min}–${verification.forecast.social_tension.max}`,
    strikeRisk: `${verification.forecast.strike_risk_pct.min}–${verification.forecast.strike_risk_pct.max}%`,
    stabilized: `${verification.forecast.stabilized_residents.min}–${verification.forecast.stabilized_residents.max}`,
  }
  const actual: DisplayMetrics = {
    highFoodRisk: String(verification.actual.high_food_risk_residents),
    socialTension: String(verification.actual.social_tension),
    strikeRisk: `${verification.actual.strike_risk_pct}%`,
    stabilized: String(verification.actual.stabilized_residents),
  }
  const control: DisplayMetrics = {
    highFoodRisk: String(verification.no_action.high_food_risk_residents),
    socialTension: String(verification.no_action.social_tension),
    strikeRisk: `${verification.no_action.strike_risk_pct}%`,
    stabilized: String(verification.no_action.stabilized_residents),
  }

  return (
    <section className="challenge-outcome" aria-labelledby="challenge-outcome-title">
      <header>
        <div>
          <span>PAIRED CONTINUING-WORLD RESULT</span>
          <h3 id="challenge-outcome-title">72-hour outcome</h3>
        </div>
        <code>{verification.receipt_id}</code>
      </header>

      <div className="challenge-outcome-columns">
        <article aria-label="Prediction">
          <span>Prediction</span>
          <MetricList metrics={prediction} />
        </article>
        <article aria-label="Actual after 72h">
          <span>Actual after 72h</span>
          <MetricList metrics={actual} />
        </article>
        <article aria-label="No-action control">
          <span>No-action control</span>
          <MetricList metrics={control} />
          {verification.no_action.strike_event_triggered
            ? <small>Strike triggered</small>
            : <small>No strike event</small>}
        </article>
      </div>

      <p className="challenge-outcome-deviation">
        <strong>Notable deviation</strong>
        {verification.notable_deviation}
      </p>

      <div className="challenge-outcome-timeline">
        <div>
          <strong>Paired simulation timeline</strong>
          <span>T+0 baseline · 12 × 6-hour ticks</span>
        </div>
        <ol aria-label="72 hour outcome timeline">
          {timeline.map((snapshot, index) => (
            <li
              data-active={index === activeIndex ? 'true' : 'false'}
              data-testid="outcome-timeline-point"
              key={`${snapshot.tick_index}:${snapshot.world_time}`}
            >
              <div>
                <strong>
                  {snapshot.elapsed_hours === 0
                    ? 'T+0 baseline'
                    : `T+${snapshot.elapsed_hours}h`}
                </strong>
                <time dateTime={snapshot.world_time}>{snapshot.world_time}</time>
              </div>
              <span>Food {snapshot.metrics.high_food_risk_residents}</span>
              <span>Tension {snapshot.metrics.social_tension}</span>
              <span>Strike {snapshot.metrics.strike_risk_pct}%</span>
              <span>Stable {snapshot.metrics.stabilized_residents}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
