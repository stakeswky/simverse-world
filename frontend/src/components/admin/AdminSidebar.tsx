type AdminTab = 'dashboard' | 'users' | 'residents' | 'forge' | 'economy' | 'system'

interface NavItem {
  key: AdminTab
  icon: string
  label: string
}

const NAV_ITEMS: NavItem[] = [
  { key: 'dashboard', icon: '📊', label: '仪表盘' },
  { key: 'users', icon: '👥', label: '用户' },
  { key: 'residents', icon: '🏠', label: '居民' },
  { key: 'forge', icon: '🔮', label: '炼化' },
  { key: 'economy', icon: '🪙', label: '经济' },
  { key: 'system', icon: '⚙️', label: '系统' },
]

interface AdminSidebarProps {
  activeTab: AdminTab
  onTabChange: (tab: AdminTab) => void
}

export function AdminSidebar({ activeTab, onTabChange }: AdminSidebarProps) {
  return (
    <div style={{
      width: 220,
      minHeight: 'calc(100vh - var(--nav-height))',
      background: 'var(--bg-card)',
      borderRight: '1px solid var(--border)',
      padding: '24px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 24,
      flexShrink: 0,
    }}>
      {/* Header */}
      <div style={{ padding: '4px 14px' }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          管理面板
        </div>
      </div>

      {/* Navigation */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV_ITEMS.map((item) => {
          const isActive = activeTab === item.key
          return (
            <button
              key={item.key}
              onClick={() => onTabChange(item.key)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '10px 14px',
                borderRadius: 8,
                background: isActive ? 'var(--bg-input)' : 'transparent',
                border: isActive ? '1px solid var(--border)' : '1px solid transparent',
                color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                fontSize: 14,
                cursor: 'pointer',
                textAlign: 'left',
                fontWeight: isActive ? 600 : 400,
                transition: 'background 0.15s, color 0.15s',
              }}
            >
              <span style={{ fontSize: 16 }}>{item.icon}</span>
              {item.label}
            </button>
          )
        })}
      </div>

      {/* Footer hint */}
      <div style={{ marginTop: 'auto', padding: '10px 14px', background: '#ef444410', borderRadius: 8 }}>
        <div style={{ fontSize: 11, color: '#ef4444', fontWeight: 600 }}>🔐 管理员专属</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>谨慎操作</div>
      </div>
    </div>
  )
}

export type { AdminTab }
