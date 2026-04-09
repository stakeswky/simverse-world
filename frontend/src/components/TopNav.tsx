import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGameStore } from '../stores/gameStore'
import { SearchDropdown } from './SearchDropdown'
import { bridge } from '../game/phaserBridge'
import { disconnectWS } from '../services/ws'

export function TopNav() {
  const user = useGameStore((s) => s.user)
  const logout = useGameStore((s) => s.logout)
  const balance = user?.soul_coin_balance ?? 0
  const navigate = useNavigate()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const avatarRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!dropdownOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (avatarRef.current && !avatarRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [dropdownOpen])

  const handleLogout = () => {
    disconnectWS()
    logout()
    navigate('/login')
  }

  return (
    <nav style={{
      position: 'fixed', top: 0, left: 0, right: 0, height: 'var(--nav-height)',
      background: 'var(--bg-card)', borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px', zIndex: 20,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <span style={{ fontWeight: 700, fontSize: 15, cursor: 'pointer' }}
              onClick={() => navigate('/')}>🏙️ Skills World</span>
        <button onClick={() => navigate('/forge')} style={{
          background: 'var(--accent-red)', color: 'white', border: 'none',
          padding: '5px 12px', borderRadius: 'var(--radius)', fontSize: 12,
          fontWeight: 600, cursor: 'pointer',
        }}>+ 炼化新居民</button>
        <button onClick={() => bridge.emit('bulletin:open')} style={{
          background: 'none', color: '#f59e0b', border: '1px solid #f59e0b44',
          padding: '5px 12px', borderRadius: 'var(--radius)', fontSize: 12,
          fontWeight: 600, cursor: 'pointer',
        }}>📋 公告板</button>
        {user?.is_admin && (
          <button onClick={() => navigate('/admin')} style={{
            background: 'none', color: '#ef4444', border: '1px solid #ef444444',
            padding: '5px 12px', borderRadius: 'var(--radius)', fontSize: 12,
            fontWeight: 600, cursor: 'pointer',
          }}>🔐 管理</button>
        )}
      </div>
      <SearchDropdown />
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{
          color: 'var(--accent-green)', fontSize: 13,
          background: '#53d76915', padding: '4px 12px', borderRadius: 16,
        }}>🪙 {balance}</span>
        <div ref={avatarRef} style={{ position: 'relative' }}>
          <div
            onClick={() => setDropdownOpen((v) => !v)}
            style={{
              width: 30, height: 30, background: 'var(--bg-input)', borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
              fontWeight: 700, color: 'var(--text-primary)', cursor: 'pointer',
              border: dropdownOpen ? '1px solid var(--accent)' : '1px solid transparent',
            }}
            title="账号菜单"
          >
            {user?.name?.[0]?.toUpperCase() || '?'}
          </div>
          {dropdownOpen && (
            <div style={{
              position: 'absolute', top: 38, right: 0,
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 8, minWidth: 160, boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
              zIndex: 100, overflow: 'hidden',
            }}>
              <div style={{
                padding: '10px 14px', fontSize: 13, fontWeight: 600,
                color: 'var(--text-primary)', borderBottom: '1px solid var(--border)',
              }}>
                {user?.name ?? '用户'}
              </div>
              <button
                onClick={() => { setDropdownOpen(false); navigate('/profile') }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '9px 14px', fontSize: 13,
                  color: 'var(--text-primary)', background: 'none', border: 'none',
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-input)' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'none' }}
              >
                👤 个人主页
              </button>
              <button
                onClick={handleLogout}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '9px 14px', fontSize: 13,
                  color: '#ff6b6b', background: 'none', border: 'none',
                  cursor: 'pointer', borderTop: '1px solid var(--border)',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-input)' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'none' }}
              >
                🚪 退出登录
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  )
}
