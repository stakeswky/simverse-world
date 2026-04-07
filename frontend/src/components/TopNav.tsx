import { useGameStore } from '../stores/gameStore'

export function TopNav() {
  const user = useGameStore((s) => s.user)
  const balance = user?.soul_coin_balance ?? 0

  return (
    <nav style={{
      position: 'fixed', top: 0, left: 0, right: 0, height: 'var(--nav-height)',
      background: 'var(--bg-card)', borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px', zIndex: 20,
    }}>
      <span style={{ fontWeight: 700, fontSize: 15 }}>🏙️ Skills World</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{
          color: 'var(--accent-green)', fontSize: 13,
          background: '#53d76915', padding: '4px 12px', borderRadius: 16,
        }}>🪙 {balance}</span>
        <div style={{
          width: 30, height: 30, background: 'var(--bg-input)', borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
        }}>👤</div>
      </div>
    </nav>
  )
}
