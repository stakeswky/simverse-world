import { useState, useRef, useEffect, useCallback } from 'react'
import { forgeStart, forgeAnswer, forgeStatus } from '../../services/api'
import type { ForgeStatusResponse } from '../../services/api'

interface ForgeChatProps {
  onStateUpdate: (state: ForgeStatusResponse) => void
  onComplete: (residentId: string) => void
}

interface ChatMessage {
  role: 'bot' | 'user'
  text: string
}

const TOTAL_STEPS = 5
const STEP_LABELS = ['', '命名', '能力', '性格', '灵魂', '素材']

export function ForgeChat({ onStateUpdate, onComplete }: ForgeChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'bot', text: '欢迎来到炼化器！在这里，你可以创造一位独一无二的 AI 居民。\n\n让我们开始吧 —— 给这位居民起个名字？' },
  ])
  const [input, setInput] = useState('')
  const [forgeId, setForgeId] = useState<string | null>(null)
  const [currentStep, setCurrentStep] = useState(1)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isDone, setIsDone] = useState(false)
  const [generatingProgress, setGeneratingProgress] = useState('')
  const [error, setError] = useState<string | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, generatingProgress])

  useEffect(() => {
    if (!isGenerating && !isDone) inputRef.current?.focus()
  }, [isGenerating, isDone, currentStep])

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current)
    }
  }, [])

  const pollStatus = useCallback((fid: string) => {
    const STAGES = [
      '正在分析能力描述...',
      '正在构建人格模型...',
      '正在提炼灵魂内核...',
      '正在评估质量等级...',
      '正在分配街区...',
    ]
    let stageIdx = 0

    pollTimerRef.current = setInterval(() => {
      void (async () => {
        try {
          const status = await forgeStatus(fid)
          onStateUpdate(status)

          if (stageIdx < STAGES.length) {
            setGeneratingProgress(STAGES[stageIdx])
            stageIdx++
          }

          if (status.status === 'done') {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current)
            setIsGenerating(false)
            setIsDone(true)
            setGeneratingProgress('')

            const stars = '⭐'.repeat(status.star_rating)
            const districtMap: Record<string, string> = {
              engineering: '工程街区', product: '产品街区',
              academy: '学院区', free: '自由区',
            }
            setMessages(prev => [...prev, {
              role: 'bot',
              text: `炼化完成！${status.name} 已成功入住 Simverse World！\n\n` +
                    `评级：${stars}\n` +
                    `街区：${districtMap[status.district] ?? status.district}\n\n` +
                    `你获得了 50 🪙 Soul Coin 奖励！`,
            }])

            if (status.resident_id) {
              setTimeout(() => onComplete(status.resident_id!), 100)
            }
          } else if (status.status === 'error') {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current)
            setIsGenerating(false)
            setError(status.error ?? '生成过程中出现错误')
            setMessages(prev => [...prev, {
              role: 'bot',
              text: `抱歉，炼化过程出现了问题：${status.error ?? '未知错误'}。请刷新页面重试。`,
            }])
          }
        } catch {
          // Network error — keep polling
        }
      })()
    }, 3000)
  }, [onStateUpdate, onComplete])

  const send = async () => {
    const text = input.trim()
    if (!text || isGenerating || isDone) return
    setInput('')
    setError(null)

    setMessages(prev => [...prev, { role: 'user', text }])

    try {
      if (!forgeId) {
        // Q1: name — call /forge/start
        const resp = await forgeStart(text)
        setForgeId(resp.forge_id)
        setCurrentStep(2)
        setMessages(prev => [...prev, { role: 'bot', text: resp.question }])
        const status = await forgeStatus(resp.forge_id)
        onStateUpdate(status)
      } else {
        // Q2-Q5 — call /forge/answer
        const resp = await forgeAnswer(forgeId, text)
        setCurrentStep(resp.step + 1)

        if (resp.next_step === null) {
          // All answered — trigger generation
          setIsGenerating(true)
          setGeneratingProgress('开始炼化...')
          setMessages(prev => [...prev, {
            role: 'bot',
            text: '所有信息已收集完毕！正在为你炼化这位居民，请稍等（约 30-60 秒）...',
          }])
          pollStatus(forgeId)
        } else {
          setMessages(prev => [...prev, { role: 'bot', text: resp.question! }])
          const status = await forgeStatus(forgeId)
          onStateUpdate(status)
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '请求失败'
      setError(msg)
      setMessages(prev => [...prev, { role: 'bot', text: `出错了：${msg}` }])
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Progress bar */}
      <div style={{
        padding: '12px 20px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600, whiteSpace: 'nowrap' }}>
          Step {Math.min(currentStep, TOTAL_STEPS)}/{TOTAL_STEPS}
        </span>
        <div style={{ flex: 1, display: 'flex', gap: 4 }}>
          {Array.from({ length: TOTAL_STEPS }, (_, i) => (
            <div key={i} style={{
              flex: 1, height: 4, borderRadius: 2,
              background: i < currentStep ? 'var(--accent-red)' : 'var(--bg-input)',
              transition: 'background 0.3s ease',
            }} />
          ))}
        </div>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          {STEP_LABELS[Math.min(currentStep, TOTAL_STEPS)] ?? ''}
        </span>
      </div>

      {/* Messages — minHeight: 0 is critical for flex overflow scrolling */}
      <div style={{
        flex: 1, minHeight: 0, overflowY: 'auto', padding: 20,
        display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        {messages.map((m, i) => (
          <div key={i} style={{ maxWidth: '80%', alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            {m.role === 'bot' && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{
                  width: 18, height: 18, background: 'var(--accent-red)', borderRadius: 4,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 9, color: 'white', fontWeight: 700,
                }}>AI</span>
                炼化师
              </div>
            )}
            <div style={{
              padding: '12px 16px', borderRadius: 12, fontSize: 14, lineHeight: 1.7,
              whiteSpace: 'pre-wrap',
              ...(m.role === 'user'
                ? { background: 'var(--accent-red)', color: 'white', borderBottomRightRadius: 4 }
                : { background: 'var(--bg-input)', color: 'var(--text-primary)', borderBottomLeftRadius: 4 }),
            }}>
              {m.text}
            </div>
          </div>
        ))}

        {isGenerating && generatingProgress && (
          <div style={{ alignSelf: 'flex-start', maxWidth: '80%' }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{
                width: 18, height: 18, background: 'var(--accent-red)', borderRadius: 4,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 9, color: 'white', fontWeight: 700,
              }}>AI</span>
              炼化师
            </div>
            <div style={{
              padding: '12px 16px', borderRadius: 12, fontSize: 14,
              background: 'var(--bg-input)', color: 'var(--text-secondary)',
              borderBottomLeftRadius: 4, display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{
                width: 14, height: 14, border: '2px solid var(--accent-red)',
                borderTopColor: 'transparent', borderRadius: '50%',
                display: 'inline-block', flexShrink: 0,
                animation: 'spin 0.8s linear infinite',
              }} />
              {generatingProgress}
            </div>
          </div>
        )}

        {error && (
          <div style={{ alignSelf: 'center', fontSize: 12, color: 'var(--accent-red)', padding: '6px 12px', background: '#e9456010', borderRadius: 6 }}>
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{ padding: '14px 20px', borderTop: '1px solid var(--border)', display: 'flex', gap: 10, alignItems: 'center' }}>
        {isDone ? (
          <button onClick={() => { window.location.href = '/' }} style={{
            flex: 1, background: 'var(--accent-green)', color: '#000', border: 'none',
            padding: '12px 20px', borderRadius: 'var(--radius)', fontSize: 14,
            fontWeight: 700, cursor: 'pointer',
          }}>
            前往城市查看新居民 →
          </button>
        ) : (
          <>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
              placeholder={isGenerating ? '正在炼化中...' : '输入你的回答...'}
              disabled={isGenerating}
              style={{
                flex: 1, background: 'var(--bg-input)', border: '1px solid var(--border)',
                color: 'var(--text-primary)', padding: '12px 16px', borderRadius: 'var(--radius)',
                fontSize: 14, outline: 'none', opacity: isGenerating ? 0.5 : 1,
              }}
            />
            <button
              onClick={() => void send()}
              disabled={isGenerating || !input.trim()}
              style={{
                background: isGenerating || !input.trim() ? 'var(--bg-input)' : 'var(--accent-red)',
                color: isGenerating || !input.trim() ? 'var(--text-muted)' : 'white',
                border: 'none', padding: '12px 20px', borderRadius: 'var(--radius)',
                fontSize: 14, fontWeight: 600, cursor: isGenerating ? 'not-allowed' : 'pointer',
                transition: 'background 0.2s',
              }}
            >
              发送
            </button>
          </>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
