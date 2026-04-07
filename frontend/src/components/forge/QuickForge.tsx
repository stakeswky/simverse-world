import { useState, useRef, useEffect, useCallback } from 'react'
import { forgeQuick, forgeStatus } from '../../services/api'
import type { ForgeStatusResponse } from '../../services/api'

interface QuickForgeProps {
  onStateUpdate: (state: ForgeStatusResponse) => void
  onComplete: (residentId: string) => void
}

const GENERATION_STAGES = [
  '正在分析人物经历...',
  '提取能力层...',
  '构建人格模型...',
  '提炼灵魂内核...',
  '评估质量 & 分配街区...',
]

const PLACEHOLDER = `在这里粘贴任何关于这个人的文字，例如：

• 个人简历 / LinkedIn 介绍
• 聊天记录片段
• 别人对他/她的评价
• 采访或文章摘录
• 你自己写的人物描述

系统会自动从文字中抽取：能力、人格、价值观。
文字越丰富，炼化结果越精准。`

export function QuickForge({ onStateUpdate, onComplete }: QuickForgeProps) {
  const [name, setName] = useState('')
  const [rawText, setRawText] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [isDone, setIsDone] = useState(false)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ForgeStatusResponse | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const stageRef = useRef(0)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const pollStatus = useCallback((forgeId: string) => {
    stageRef.current = 0
    pollRef.current = setInterval(async () => {
      try {
        const status = await forgeStatus(forgeId)
        onStateUpdate(status)

        if (stageRef.current < GENERATION_STAGES.length) {
          setProgress(GENERATION_STAGES[stageRef.current])
          stageRef.current++
        }

        if (status.status === 'done') {
          clearInterval(pollRef.current!)
          setIsGenerating(false)
          setIsDone(true)
          setProgress('')
          setResult(status)
          if (status.resident_id) setTimeout(() => onComplete(status.resident_id!), 300)
        } else if (status.status === 'error') {
          clearInterval(pollRef.current!)
          setIsGenerating(false)
          setError(status.error ?? '生成失败，请重试')
        }
      } catch { /* keep polling */ }
    }, 3000)
  }, [onStateUpdate, onComplete])

  const handleSubmit = async () => {
    if (!name.trim() || !rawText.trim()) {
      setError('请填写姓名和文字内容')
      return
    }
    setError(null)
    setIsGenerating(true)
    setProgress('开始提取...')

    try {
      const { forge_id } = await forgeQuick(name.trim(), rawText.trim())
      pollStatus(forge_id)
    } catch (e) {
      setIsGenerating(false)
      setError(e instanceof Error ? e.message : '请求失败')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}>
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 2 }}>⚡ 快速提取</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          粘贴任意文字 → 自动提炼三层 Skill
        </div>
      </div>

      {/* Scrollable form area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>

        {/* Name */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>
            居民姓名 *
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如：张三 / 埃隆·马斯克 / 诸葛亮"
            disabled={isGenerating || isDone}
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              color: 'var(--text-primary)', padding: '10px 14px',
              borderRadius: 'var(--radius)', fontSize: 14, outline: 'none',
            }}
          />
        </div>

        {/* Raw text */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>
            人物文字材料 *
          </label>
          <textarea
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder={PLACEHOLDER}
            disabled={isGenerating || isDone}
            rows={14}
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              color: 'var(--text-primary)', padding: '12px 14px',
              borderRadius: 'var(--radius)', fontSize: 13, outline: 'none',
              resize: 'vertical', lineHeight: 1.7,
              fontFamily: 'inherit',
            }}
          />
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, textAlign: 'right' }}>
            {rawText.length} 字
          </div>
        </div>

        {/* Tips */}
        {!isGenerating && !isDone && (
          <div style={{
            background: '#0ea5e910', border: '1px solid #0ea5e930',
            borderRadius: 8, padding: '12px 14px', marginBottom: 16,
            fontSize: 12, color: '#0ea5e9', lineHeight: 1.7,
          }}>
            💡 <strong>提示：</strong>文字越丰富，结果越好。100字以上效果明显，500字以上效果极佳。
            中英文都支持。
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            background: '#e9456015', border: '1px solid #e9456030',
            borderRadius: 8, padding: '10px 14px', marginBottom: 16,
            fontSize: 12, color: 'var(--accent-red)',
          }}>
            {error}
          </div>
        )}

        {/* Generating progress */}
        {isGenerating && (
          <div style={{
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '16px 18px',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <span style={{
              width: 18, height: 18,
              border: '2px solid var(--accent-red)', borderTopColor: 'transparent',
              borderRadius: '50%', display: 'inline-block', flexShrink: 0,
              animation: 'spin 0.8s linear infinite',
            }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>正在炼化中...</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{progress}</div>
            </div>
          </div>
        )}

        {/* Done */}
        {isDone && result && (
          <div style={{
            background: '#53d76915', border: '1px solid #53d76940',
            borderRadius: 10, padding: '16px 18px',
          }}>
            <div style={{ fontWeight: 700, color: 'var(--accent-green)', fontSize: 15, marginBottom: 6 }}>
              ✅ 炼化完成！
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              <strong>{result.name}</strong> 已入住{' '}
              {({ engineering: '工程街区', product: '产品街区', academy: '学院区', free: '自由区' })[result.district] ?? result.district}
              <br />
              质量评级：{'⭐'.repeat(result.star_rating)}
              <br />
              你获得了 <strong style={{ color: 'var(--accent-green)' }}>50 🪙</strong> 奖励！
            </div>
            <button
              onClick={() => onComplete(result.resident_id ?? '')}
              style={{
                marginTop: 12, background: 'var(--accent-green)', color: '#000',
                border: 'none', padding: '10px 20px', borderRadius: 'var(--radius)',
                fontSize: 13, fontWeight: 700, cursor: 'pointer', width: '100%',
              }}
            >
              前往城市查看新居民 →
            </button>
          </div>
        )}
      </div>

      {/* Submit button — fixed at bottom */}
      {!isDone && (
        <div style={{
          padding: '14px 20px',
          borderTop: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <button
            onClick={() => void handleSubmit()}
            disabled={isGenerating || !name.trim() || !rawText.trim()}
            style={{
              width: '100%',
              background: isGenerating || !name.trim() || !rawText.trim()
                ? 'var(--bg-input)' : 'var(--accent-red)',
              color: isGenerating || !name.trim() || !rawText.trim()
                ? 'var(--text-muted)' : 'white',
              border: 'none', padding: '12px 20px',
              borderRadius: 'var(--radius)', fontSize: 14,
              fontWeight: 700, cursor: isGenerating ? 'not-allowed' : 'pointer',
              transition: 'background 0.2s',
            }}
          >
            {isGenerating ? '炼化中...' : '⚡ 立即提取 Skill'}
          </button>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
