import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopNav } from '../components/TopNav'
import { ForgeChat } from '../components/forge/ForgeChat'
import { ForgePreview } from '../components/forge/ForgePreview'
import { QuickForge } from '../components/forge/QuickForge'
import { DeepForge } from '../components/forge/DeepForge'
import type { ForgeStatusResponse, DeepForgeStatusResponse } from '../services/api'

type Mode = 'guided' | 'quick' | 'deep'

export function ForgePage() {
  const navigate = useNavigate()
  const [forgeState, setForgeState] = useState<ForgeStatusResponse | null>(null)
  const [mode, setMode] = useState<Mode>('guided')

  const handleStateUpdate = useCallback((state: ForgeStatusResponse | DeepForgeStatusResponse) => {
    // ForgePreview uses ForgeStatusResponse shape; DeepForgeStatusResponse is compatible for preview
    setForgeState(state as ForgeStatusResponse)
  }, [])

  const handleComplete = useCallback((_residentId: string) => {
    navigate('/')
  }, [navigate])

  return (
    <div style={{
      height: '100vh',
      background: 'var(--bg-page)',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <TopNav />

      {/* Breadcrumb + mode switcher */}
      <div style={{
        marginTop: 'var(--nav-height)',
        padding: '10px 24px',
        borderBottom: '1px solid var(--border)',
        fontSize: 13,
        color: 'var(--text-muted)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ cursor: 'pointer', color: 'var(--accent-blue)' }} onClick={() => navigate('/')}>
            Skills World
          </span>
          <span>/</span>
          <span style={{ color: 'var(--text-primary)' }}>炼化新居民</span>
        </div>

        {/* Mode tabs */}
        <div style={{ display: 'flex', background: 'var(--bg-input)', borderRadius: 8, padding: 3, gap: 2 }}>
          {([
            { key: 'guided', label: '📝 引导式炼化', desc: '5步问答引导' },
            { key: 'quick',  label: '⚡ 快速炼化',   desc: '粘贴文本即提取' },
            { key: 'deep',   label: '🧪 深度蒸馏',   desc: '多阶段 AI 管线' },
          ] as { key: Mode; label: string; desc: string }[]).map((m) => (
            <button
              key={m.key}
              onClick={() => { setMode(m.key); setForgeState(null) }}
              title={m.desc}
              style={{
                padding: '5px 14px',
                borderRadius: 6,
                border: 'none',
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: 600,
                background: mode === m.key
                  ? m.key === 'deep'
                    ? 'linear-gradient(135deg, #8b5cf6, #6d28d9)'
                    : 'var(--accent-red)'
                  : 'transparent',
                color: mode === m.key ? 'white' : 'var(--text-muted)',
                transition: 'all 0.15s',
              }}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main split layout — fills remaining height, inner panels scroll */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* Left panel */}
        <div style={{
          flex: 1,
          minWidth: 0,
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          {mode === 'guided' && (
            <ForgeChat onStateUpdate={handleStateUpdate} onComplete={handleComplete} />
          )}
          {mode === 'quick' && (
            <QuickForge onStateUpdate={handleStateUpdate} onComplete={handleComplete} />
          )}
          {mode === 'deep' && (
            <DeepForge onStateUpdate={handleStateUpdate} onComplete={handleComplete} />
          )}
        </div>

        {/* Right preview */}
        <div style={{
          width: 460,
          minWidth: 340,
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--bg-card)',
          overflow: 'hidden',
        }}>
          <ForgePreview state={forgeState} />
        </div>
      </div>
    </div>
  )
}
