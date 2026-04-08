import { useNavigate } from 'react-router-dom'
import { useGameStore } from '../stores/gameStore'
import { SearchDropdown } from './SearchDropdown'
import { bridge } from '../game/phaserBridge'

export function TopNav() {
  const user = useGameStore((s) => s.user)
  const balance = user?.soul_coin_balance ?? 0
  const navigate = useNavigate()

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
        <div
          onClick={() => navigate('/profile')}
          style={{
            width: 30, height: 30, background: 'var(--bg-input)', borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
            fontWeight: 700, color: 'var(--text-primary)', cursor: 'pointer',
          }}
          title="个人主页"
        >
          {user?.name?.[0]?.toUpperCase() || '?'}
        </div>
      </div>
    </nav>
  )
}
