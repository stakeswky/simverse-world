import { useGameStore } from '../../stores/gameStore'

type Tab = 'residents' | 'conversations' | 'transactions' | 'settings'

const NAV_ITEMS: { key: Tab; icon: string; label: string }[] = [
  { key: 'residents', icon: '🏠', label: '我的居民' },
  { key: 'conversations', icon: '💬', label: '对话历史' },
  { key: 'transactions', icon: '🪙', label: '代币明细' },
  { key: 'settings', icon: '⚙️', label: '设置' },
]

export function ProfileSidebar({ residentCount }: { residentCount: number }) {
  const user = useGameStore((s) => s.user)
  const profileTab = useGameStore((s) => s.profileTab)
  const setProfileTab = useGameStore((s) => s.setProfileTab)

  return (
    <div style={{
      width: 250, minHeight: 'calc(100vh - var(--nav-height))',
      background: 'var(--bg-card)', borderRight: '1px solid var(--border)',
      padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 24,
    }}>
      {/* User info */}
      <div style={{ textAlign: 'center' }}>
        <div style={{
          width: 72, height: 72, background: 'var(--bg-input)', borderRadius: 12,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 32, margin: '0 auto 12px',
        }}>
          👤
        </div>
        <div style={{ fontWeight: 700, fontSize: 16 }}>{user?.name}</div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
          创作了 {residentCount} 位居民
        </div>
      </div>

      {/* Navigation */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV_ITEMS.map((item) => (
          <button key={item.key} onClick={() => setProfileTab(item.key)} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
            borderRadius: 8, background: profileTab === item.key ? 'var(--bg-input)' : 'transparent',
            border: 'none', color: profileTab === item.key ? 'var(--text-primary)' : 'var(--text-secondary)',
            fontSize: 14, cursor: 'pointer', textAlign: 'left',
            fontWeight: profileTab === item.key ? 600 : 400,
          }}>
            <span style={{ fontSize: 16 }}>{item.icon}</span>{item.label}
          </button>
        ))}
      </div>

      {/* Soul Coin balance */}
      <div style={{ marginTop: 'auto', padding: '12px 14px', background: '#53d76910', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 18 }}>🪙</span>
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Soul Coin</div>
          <div style={{ fontWeight: 700, color: 'var(--accent-green)', fontSize: 16 }}>{user?.soul_coin_balance ?? 0}</div>
        </div>
      </div>
    </div>
  )
}
