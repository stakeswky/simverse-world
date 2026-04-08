import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { TopNav } from '../components/TopNav'
import { AdminSidebar, type AdminTab } from '../components/admin/AdminSidebar'
import { DashboardPanel } from '../components/admin/DashboardPanel'
import { UsersPanel } from '../components/admin/UsersPanel'
import { ResidentsPanel } from '../components/admin/ResidentsPanel'
import { ForgeMonitorPanel } from '../components/admin/ForgeMonitorPanel'
import { EconomyPanel } from '../components/admin/EconomyPanel'
import { SystemConfigPanel } from '../components/admin/SystemConfigPanel'
import { useGameStore } from '../stores/gameStore'

export function AdminPage() {
  const user = useGameStore((s) => s.user)
  const token = useGameStore((s) => s.token)
  const [activeTab, setActiveTab] = useState<AdminTab>('dashboard')

  // Route guard: non-admin users are redirected to home
  if (!user?.is_admin) {
    return <Navigate to="/" replace />
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardPanel />
      case 'users':
        return token ? <UsersPanel token={token} /> : null
      case 'residents':
        return token ? <ResidentsPanel token={token} /> : null
      case 'forge':
        return token ? <ForgeMonitorPanel token={token} /> : null
      case 'economy':
        return token ? <EconomyPanel token={token} /> : null
      case 'system':
        return token ? <SystemConfigPanel token={token} /> : null
      default:
        return <DashboardPanel />
    }
  }

  return (
    <>
      <TopNav />
      <div style={{
        marginTop: 'var(--nav-height)',
        display: 'flex',
        height: 'calc(100vh - var(--nav-height))',
        overflow: 'hidden',
      }}>
        <AdminSidebar activeTab={activeTab} onTabChange={setActiveTab} />
        <div style={{
          flex: 1,
          padding: 32,
          overflowY: 'auto',
          background: 'var(--bg-base)',
        }}>
          {renderContent()}
        </div>
      </div>
    </>
  )
}
