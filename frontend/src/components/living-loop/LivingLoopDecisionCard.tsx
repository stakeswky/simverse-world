import { useEffect, useRef } from 'react'
import type {
  LivingLoopChoice,
  LivingLoopChoiceKey,
  LivingLoopDecision,
} from '../../services/api'

const EFFECT_LABELS: Record<string, string> = {
  worker_trust_delta: '工人信任',
  management_trust_delta: '管理方信任',
  city_credit_delta: '城市信用',
}

interface LivingLoopDecisionCardProps {
  decision: LivingLoopDecision
  selectedChoice: LivingLoopChoiceKey | null
  submitting: boolean
  submitError: string | null
  remainingMs: number | null
  onSelect: (choice: LivingLoopChoice) => void
  onConfirm: () => void
}

function formatDelta(value: number): string {
  return `${value > 0 ? '+' : ''}${value}`
}

function ImmediateResult({ decision }: { decision: LivingLoopDecision }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const focusedDecisionRef = useRef<string | null>(null)
  const result = decision.immediate_result
  const delayedVisible = Boolean(decision.delayed_result)

  useEffect(() => {
    if (!result || delayedVisible || focusedDecisionRef.current === decision.id) return
    focusedDecisionRef.current = decision.id
    headingRef.current?.focus()
  }, [decision.id, delayedVisible, result])

  if (!result) return null

  const effects = Object.entries(result.effects ?? {})
  const impacts = result.impacts ?? []

  return (
    <section className="today-result today-result--immediate" aria-labelledby="today-immediate-title">
      <p className="today-eyebrow">CHOICE SAVED</p>
      <h3 id="today-immediate-title" ref={headingRef} tabIndex={-1}>{result.title}</h3>
      <p>{result.summary}</p>
      {(effects.length > 0 || impacts.length > 0) && (
        <ul className="today-impact-list" aria-label="服务端确认的立即影响">
          {effects.map(([key, value]) => (
            <li key={key}>
              <strong>{`${EFFECT_LABELS[key] ?? key} ${formatDelta(value)}`}</strong>
            </li>
          ))}
          {impacts.map((impact) => <li key={impact}>{impact}</li>)}
        </ul>
      )}
      <p className="today-result__scope">这次选择已真实保存；这些数值只描述本次事件，不会改写全局经济或关系。</p>
    </section>
  )
}

function WaitingResult({ decision, remainingMs }: {
  decision: LivingLoopDecision
  remainingMs: number | null
}) {
  if (!decision.result_available_at || decision.delayed_result) return null

  const totalSeconds = Math.max(0, Math.ceil((remainingMs ?? 0) / 1_000))
  const hours = Math.floor(totalSeconds / 3_600)
  const minutes = Math.floor((totalSeconds % 3_600) / 60)
  const seconds = totalSeconds % 60
  const remaining = hours > 0
    ? `${hours} 小时 ${minutes} 分`
    : `${minutes} 分 ${seconds} 秒`

  return (
    <section className="today-waiting" aria-labelledby="today-waiting-title">
      <p className="today-eyebrow">OUTCOME PENDING</p>
      <h3 id="today-waiting-title">后续仍在小镇里发生</h3>
      <p>到时间后会重新向服务端确认结果，不会在浏览器里提前推演。</p>
      <div className="today-timer" role="timer" aria-label="延迟后果可查看时间" aria-live="off">
        <span>预计还需</span>
        <strong>{remaining}</strong>
        <time dateTime={decision.result_available_at}>
          {new Intl.DateTimeFormat('zh-CN', {
            timeZone: 'UTC',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          }).format(new Date(decision.result_available_at))} UTC
        </time>
      </div>
    </section>
  )
}

function DelayedResult({ decision }: { decision: LivingLoopDecision }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const focusedDecisionRef = useRef<string | null>(null)
  const result = decision.delayed_result

  useEffect(() => {
    if (!result || focusedDecisionRef.current === decision.id) return
    focusedDecisionRef.current = decision.id
    headingRef.current?.focus()
  }, [decision.id, result])

  if (!result) return null

  return (
    <section className="today-result today-result--delayed" aria-labelledby="today-delayed-title">
      <p className="today-eyebrow">THE TOWN ANSWERED</p>
      <h3 id="today-delayed-title" ref={headingRef} tabIndex={-1}>{result.title}</h3>
      <p>{result.summary}</p>
      <span className="today-result__state">
        {decision.state === 'result_viewed' ? '结果已查看并保存' : '结果已经到达'}
      </span>
    </section>
  )
}

export function LivingLoopDecisionCard({
  decision,
  selectedChoice,
  submitting,
  submitError,
  remainingMs,
  onSelect,
  onConfirm,
}: LivingLoopDecisionCardProps) {
  const selected = decision.choices.find((choice) => choice.key === selectedChoice) ?? null
  const pending = decision.state === 'pending'

  return (
    <fieldset className="today-decision" aria-describedby="today-decision-context">
      <legend>今天最重要的一件事</legend>
      <div className="today-decision__heading">
        <p className="today-eyebrow">ONE DECISION / REAL CONSEQUENCES</p>
        <h2>{decision.title}</h2>
        <p id="today-decision-context">{decision.context}</p>
      </div>

      <ul className="today-stakes" aria-label="事件风险">
        {decision.stakes.map((stake) => <li key={stake}>{stake}</li>)}
      </ul>

      {pending ? (
        <div className="today-choice-grid">
          {decision.choices.map((choice) => (
            <label className="today-choice" key={choice.key}>
              <input
                type="radio"
                name="living-loop-choice"
                value={choice.key}
                checked={selectedChoice === choice.key}
                disabled={submitting}
                onChange={() => onSelect(choice)}
              />
              <span className="today-choice__marker" aria-hidden="true" />
              <span className="today-choice__copy">
                <strong>{choice.label}</strong>
                <span>{choice.summary}</span>
                <span className="today-choice__risk">风险：{choice.risk}</span>
                <span className="today-choice__tradeoffs">{choice.tradeoffs.join(' · ')}</span>
              </span>
            </label>
          ))}
        </div>
      ) : (
        <div className="today-selected-choice">
          <span>你今天选择了</span>
          <strong>{decision.choices.find((choice) => choice.key === decision.selected_choice)?.label ?? '已保存的选项'}</strong>
        </div>
      )}

      {pending && selected && (
        <section className="today-confirmation" role="region" aria-label="确认今天的选择">
          <div>
            <p className="today-eyebrow">CONFIRM YOUR CHOICE</p>
            <h3>{selected.label}</h3>
            <p>{selected.summary}</p>
            <p className="today-confirmation__risk"><strong>明示风险：</strong>{selected.risk}</p>
            <ul>
              {selected.tradeoffs.map((tradeoff) => <li key={tradeoff}>{tradeoff}</li>)}
            </ul>
          </div>
          <button type="button" disabled={submitting} onClick={onConfirm}>
            {submitting ? '正在保存…' : '确认这个选择'}
          </button>
        </section>
      )}

      {submitError && <div className="today-inline-error" role="alert">{submitError}</div>}
      <ImmediateResult decision={decision} />
      <WaitingResult decision={decision} remainingMs={remainingMs} />
      <DelayedResult decision={decision} />
    </fieldset>
  )
}
