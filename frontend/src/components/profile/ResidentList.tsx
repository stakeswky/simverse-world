import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGameStore } from '../../stores/gameStore'
import { ResidentCard } from './ResidentCard'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface ResidentItem {
  id: string; slug: string; name: string; star_rating: number; status: string;
  heat: number; district: string; total_conversations: number; avg_rating: number;
  sprite_key: string; meta_json: { role?: string } | null;
}

export function ResidentList({ onResidentCountChange, onEditResident }: { onResidentCountChange: (n: number) => void; onEditResident: (slug: string) => void }) {
  const [residents, setResidents] = useState<ResidentItem[]>([])
  const [loading, setLoading] = useState(true)
  const token = useGameStore((s) => s.token)
  const navigate = useNavigate()

  useEffect(() => {
    void (async () => {
      setLoading(true)
      try {
        const resp = await fetch(`${API}/profile/residents`, { headers: { Authorization: `Bearer ${token ?? ''}` } })
        if (resp.ok) { const data = await resp.json(); setResidents(data); onResidentCountChange(data.length) }
      } catch { /* ignore */ } finally { setLoading(false) }
    })()
  }, [token])

  if (loading) return <div style={{ color: 'var(--text-muted)', padding: 20, textAlign: 'center' }}>加载中...</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700 }}>我的居民</h2>
        <button onClick={() => navigate('/forge')} style={{ background: 'var(--accent-red)', color: 'white', border: 'none', padding: '8px 18px', borderRadius: 'var(--radius)', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>+ 创建新居民</button>
      </div>
      {residents.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🏘️</div>
          <div>还没有创建任何居民</div>
          <button onClick={() => navigate('/forge')} style={{ marginTop: 16, background: 'var(--accent-red)', color: 'white', border: 'none', padding: '10px 24px', borderRadius: 'var(--radius)', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>创建第一位居民</button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {residents.map((r) => <ResidentCard key={r.id} resident={r} onEdit={onEditResident} />)}
        </div>
      )}
    </div>
  )
}
