import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopNav } from '../components/TopNav'
import { ForgeChat } from '../components/forge/ForgeChat'
import { ForgePreview } from '../components/forge/ForgePreview'
import type { ForgeStatusResponse } from '../services/api'

export function ForgePage() {
  const navigate = useNavigate()
  const [forgeState, setForgeState] = useState<ForgeStatusResponse | null>(null)

  const handleStateUpdate = useCallback((state: ForgeStatusResponse) => {
    setForgeState(state)
  }, [])

  const handleComplete = useCallback((_residentId: string) => {
    navigate('/')
  }, [navigate])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-page)', display: 'flex', flexDirection: 'column' }}>
      <TopNav />
      <div style={{
        marginTop: 'var(--nav-height)', padding: '12px 24px',
        borderBottom: '1px solid var(--border)', fontSize: 13,
        color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ cursor: 'pointer', color: 'var(--accent-blue)' }} onClick={() => navigate('/')}>
          Skills World
        </span>
        <span>/</span>
        <span style={{ color: 'var(--text-primary)' }}>炼化新居民</span>
      </div>
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ flex: 1, minWidth: 0, borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column' }}>
          <ForgeChat onStateUpdate={handleStateUpdate} onComplete={handleComplete} />
        </div>
        <div style={{ width: 480, minWidth: 380, flexShrink: 0, display: 'flex', flexDirection: 'column', background: 'var(--bg-card)' }}>
          <ForgePreview state={forgeState} />
        </div>
      </div>
    </div>
  )
}
