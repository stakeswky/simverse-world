import { useState, useRef, useEffect, useCallback } from 'react'
import { deepForgeStart, deepForgeStatus, apiFetch } from '../../services/api'
import type { DeepForgeStage, DeepForgeStatusResponse } from '../../services/api'
import { useGameStore } from '../../stores/gameStore'

interface DeepForgeProps {
  onStateUpdate?: (state: DeepForgeStatusResponse) => void
  onComplete?: (residentId: string) => void
}

interface StageInfo {
  key: DeepForgeStage
  label: string
  icon: string
}

const STAGES: StageInfo[] = [
  { key: 'routing',     label: '路由中',  icon: '🔀' },
  { key: 'researching', label: '调研中',  icon: '🔍' },
  { key: 'extracting',  label: '提取中',  icon: '⚗️' },
  { key: 'building',    label: '构建中',  icon: '🏗️' },
  { key: 'validating',  label: '验证中',  icon: '✅' },
  { key: 'refining',    label: '精炼中',  icon: '💎' },
  { key: 'done',        label: '完成',    icon: '🎉' },
]

type UIStatus = 'idle' | 'running' | 'done' | 'error'

function getStageIndex(stage: DeepForgeStage): number {
  return STAGES.findIndex((s) => s.key === stage)
}

export function DeepForge({ onStateUpdate, onComplete }: DeepForgeProps) {
  const [characterName, setCharacterName] = useState('')
  const [userMaterial, setUserMaterial] = useState('')
  const [uiStatus, setUiStatus] = useState<UIStatus>('idle')
  const [currentStage, setCurrentStage] = useState<DeepForgeStage | null>(null)
  const [result, setResult] = useState<DeepForgeStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const forgeIdRef = useRef<string | null>(null)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const pollStatus = useCallback((forgeId: string) => {
    const token = localStorage.getItem('token') ?? ''

    pollRef.current = setInterval(() => {
      void (async () => {
        try {
          const status = await deepForgeStatus(token, forgeId)
          onStateUpdate?.(status)

          const stage = status.stage ?? status.status
          setCurrentStage(stage)

          if (stage === 'done') {
            clearInterval(pollRef.current!)
            setUiStatus('done')
            setResult(status)
            // Refresh balance (forge reward was added server-side)
            const token = useGameStore.getState().token
            if (token) {
              apiFetch<{ soul_coin_balance: number }>('/users/me', {
                headers: { Authorization: `Bearer ${token}` },
              }).then((u) => useGameStore.getState().updateBalance(u.soul_coin_balance)).catch(() => {})
            }
            if (status.resident_id) {
              setTimeout(() => onComplete?.(status.resident_id!), 300)
            }
          } else if (stage === 'error') {
            clearInterval(pollRef.current!)
            setUiStatus('error')
            setError(status.error ?? '深度蒸馏过程中出现错误')
          }
        } catch {
          // Network error — keep polling
        }
      })()
    }, 3000)
  }, [onStateUpdate, onComplete])

  const handleStart = async () => {
    if (!characterName.trim()) return
    setError(null)
    setUiStatus('running')
    setCurrentStage('routing')

    const token = localStorage.getItem('token') ?? ''

    try {
      const resp = await deepForgeStart(token, {
        character_name: characterName.trim(),
        user_material: userMaterial.trim() || undefined,
      })
      forgeIdRef.current = resp.forge_id
      pollStatus(resp.forge_id)
    } catch (e) {
      setUiStatus('error')
      setError(e instanceof Error ? e.message : '请求失败，请重试')
    }
  }

  const handleRetry = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    setUiStatus('idle')
    setCurrentStage(null)
    setResult(null)
    setError(null)
    forgeIdRef.current = null
  }

  const activeStageIdx = currentStage ? getStageIndex(currentStage) : -1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 2 }}>🧪 深度蒸馏</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          多阶段 AI 管线 · 全自动调研 + 萃取 + 精炼
        </div>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '20px' }}>

        {/* Input form — hidden once running */}
        {uiStatus === 'idle' && (
          <>
            <div style={{ marginBottom: 16 }}>
              <label style={{
                fontSize: 12, color: 'var(--text-muted)', display: 'block',
                marginBottom: 6, fontWeight: 600, letterSpacing: '0.3px',
              }}>
                角色名称 *
              </label>
              <input
                value={characterName}
                onChange={(e) => setCharacterName(e.target.value)}
                placeholder="例如：埃隆·马斯克 / 诸葛亮 / 特斯拉"
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  color: 'var(--text-primary)', padding: '10px 14px',
                  borderRadius: 'var(--radius)', fontSize: 14, outline: 'none',
                }}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{
                fontSize: 12, color: 'var(--text-muted)', display: 'block',
                marginBottom: 6, fontWeight: 600, letterSpacing: '0.3px',
              }}>
                补充素材
                <span style={{ fontWeight: 400, marginLeft: 6, opacity: 0.7 }}>（可选）</span>
              </label>
              <textarea
                value={userMaterial}
                onChange={(e) => setUserMaterial(e.target.value)}
                placeholder={`粘贴任何关于此角色的文字材料，例如：\n\n• 人物传记 / 维基百科摘要\n• 采访内容 / 语录集\n• 自传或书信\n• 别人对他/她的评价\n\n留空时系统将自动联网调研。`}
                rows={10}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  color: 'var(--text-primary)', padding: '12px 14px',
                  borderRadius: 'var(--radius)', fontSize: 13, outline: 'none',
                  resize: 'vertical', lineHeight: 1.7, fontFamily: 'inherit',
                }}
              />
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, textAlign: 'right' }}>
                {userMaterial.length} 字
              </div>
            </div>

            {/* Info box */}
            <div style={{
              background: '#8b5cf610', border: '1px solid #8b5cf630',
              borderRadius: 8, padding: '12px 14px', marginBottom: 4,
              fontSize: 12, color: '#a78bfa', lineHeight: 1.7,
            }}>
              🧪 <strong>深度蒸馏</strong>比快速炼化更彻底：系统将逐步调研、提取、验证并精炼角色的三层 Skill。
              预计耗时 <strong>60–120 秒</strong>。
            </div>
          </>
        )}

        {/* Running: stage indicator */}
        {(uiStatus === 'running' || uiStatus === 'done') && (
          <div style={{ marginBottom: 20 }}>
            {/* Character name display */}
            <div style={{
              fontSize: 14, fontWeight: 700, marginBottom: 16,
              color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{
                width: 28, height: 28, background: 'linear-gradient(135deg, #8b5cf6, #6d28d9)',
                borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, color: 'white', fontWeight: 700, flexShrink: 0,
              }}>深</span>
              正在蒸馏：{characterName}
            </div>

            {/* Stage list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {STAGES.map((s, idx) => {
                const isActive = idx === activeStageIdx && uiStatus === 'running'
                const isDone = idx < activeStageIdx || (uiStatus === 'done' && s.key !== 'error')
                const isWaiting = idx > activeStageIdx

                return (
                  <div
                    key={s.key}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12,
                      padding: '10px 14px', borderRadius: 8,
                      border: `1px solid ${isActive ? '#8b5cf680' : 'var(--border)'}`,
                      background: isActive ? '#8b5cf610' : isDone ? '#53d76908' : 'var(--bg-input)',
                      transition: 'all 0.3s ease',
                    }}
                  >
                    {/* Status icon */}
                    <div style={{ width: 20, flexShrink: 0, textAlign: 'center' }}>
                      {isActive ? (
                        <span style={{
                          display: 'inline-block',
                          width: 14, height: 14,
                          border: '2px solid #8b5cf6', borderTopColor: 'transparent',
                          borderRadius: '50%',
                          animation: 'deepSpin 0.8s linear infinite',
                        }} />
                      ) : isDone ? (
                        <span style={{ color: 'var(--accent-green)', fontSize: 13 }}>✓</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>○</span>
                      )}
                    </div>

                    {/* Stage emoji */}
                    <span style={{ fontSize: 16, flexShrink: 0 }}>{s.icon}</span>

                    {/* Label */}
                    <span style={{
                      flex: 1, fontSize: 13, fontWeight: isActive ? 700 : 500,
                      color: isActive
                        ? '#a78bfa'
                        : isDone
                          ? 'var(--text-secondary)'
                          : isWaiting
                            ? 'var(--text-muted)'
                            : 'var(--text-primary)',
                    }}>
                      {s.label}
                    </span>

                    {/* Status badge */}
                    <span style={{
                      fontSize: 10, padding: '2px 8px', borderRadius: 4,
                      background: isActive
                        ? '#8b5cf620'
                        : isDone
                          ? '#53d76920'
                          : 'transparent',
                      color: isActive ? '#a78bfa' : isDone ? 'var(--accent-green)' : 'transparent',
                      fontWeight: 600,
                    }}>
                      {isActive ? '进行中' : isDone ? '完成' : ''}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Error state */}
        {uiStatus === 'error' && (
          <div style={{
            background: '#e9456015', border: '1px solid #e9456040',
            borderRadius: 10, padding: '16px 18px', marginBottom: 16,
          }}>
            <div style={{ fontWeight: 700, color: 'var(--accent-red)', fontSize: 14, marginBottom: 6 }}>
              深度蒸馏失败
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {error}
            </div>
          </div>
        )}

        {/* Done success */}
        {uiStatus === 'done' && result && (
          <div style={{
            background: '#53d76915', border: '1px solid #53d76940',
            borderRadius: 10, padding: '16px 18px', marginTop: 4,
          }}>
            <div style={{ fontWeight: 700, color: 'var(--accent-green)', fontSize: 15, marginBottom: 6 }}>
              蒸馏完成！
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              <strong>{result.name}</strong> 已入住{' '}
              {({ engineering: '工程街区', product: '产品街区', academy: '学院区', free: '自由区' })[result.district] ?? result.district}
              <br />
              质量评级：{'⭐'.repeat(result.star_rating)}
              <br />
              你获得了 <strong style={{ color: 'var(--accent-green)' }}>50 🪙</strong> 奖励！
            </div>
            <button
              onClick={() => onComplete?.(result.resident_id ?? '')}
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

      {/* Action bar */}
      {uiStatus !== 'done' && (
        <div style={{ padding: '14px 20px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
          {uiStatus === 'error' ? (
            <button
              onClick={handleRetry}
              style={{
                width: '100%', background: 'var(--accent-red)', color: 'white',
                border: 'none', padding: '12px 20px', borderRadius: 'var(--radius)',
                fontSize: 14, fontWeight: 700, cursor: 'pointer',
              }}
            >
              重试
            </button>
          ) : uiStatus === 'running' ? (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 14px', background: '#8b5cf610',
              borderRadius: 'var(--radius)', border: '1px solid #8b5cf630',
            }}>
              <span style={{
                width: 16, height: 16,
                border: '2px solid #8b5cf6', borderTopColor: 'transparent',
                borderRadius: '50%', display: 'inline-block', flexShrink: 0,
                animation: 'deepSpin 0.8s linear infinite',
              }} />
              <span style={{ fontSize: 13, color: '#a78bfa', fontWeight: 600 }}>
                深度蒸馏进行中，请耐心等待…
              </span>
            </div>
          ) : (
            <button
              onClick={() => void handleStart()}
              disabled={!characterName.trim()}
              style={{
                width: '100%',
                background: !characterName.trim() ? 'var(--bg-input)' : 'linear-gradient(135deg, #8b5cf6, #6d28d9)',
                color: !characterName.trim() ? 'var(--text-muted)' : 'white',
                border: 'none', padding: '12px 20px', borderRadius: 'var(--radius)',
                fontSize: 14, fontWeight: 700,
                cursor: !characterName.trim() ? 'not-allowed' : 'pointer',
                transition: 'opacity 0.2s',
              }}
            >
              🧪 开始深度蒸馏
            </button>
          )}
        </div>
      )}

      <style>{`@keyframes deepSpin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
