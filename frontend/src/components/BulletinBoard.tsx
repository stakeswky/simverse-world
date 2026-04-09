import { useState, useEffect } from 'react'
import { bridge } from '../game/phaserBridge'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface BulletinResident {
  id: string
  slug: string
  name: string
  district: string
  status: string
  heat: number
  tile_x: number
  tile_y: number
  star_rating: number
  token_cost_per_turn: number
  meta_json: { role?: string } | null
}

interface BulletinData {
  hot_residents: BulletinResident[]
  new_residents: BulletinResident[]
  recent_conversations_24h: number
}

const DISTRICT_NAMES: Record<string, string> = {
  engineering: '工程街区',
  product: '产品街区',
  academy: '学院区',
  free: '自由区',
}

export function BulletinBoard() {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<BulletinData | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const unsub1 = bridge.on('bulletin:open', () => {
      setOpen(true)
      void fetchBulletin()
    })
    const unsub2 = bridge.on('bulletin:close', () => setOpen(false))
    return () => {
      unsub1()
      unsub2()
    }
  }, [])

  const fetchBulletin = async () => {
    setLoading(true)
    try {
      const resp = await fetch(`${API}/bulletin`)
      if (resp.ok) setData(await resp.json())
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }

  const navigateTo = (r: BulletinResident) => {
    bridge.emit('camera:pan', { tile_x: r.tile_x, tile_y: r.tile_y, slug: r.slug })
    setOpen(false)
  }

  if (!open) return null

  return (
    <div style={{
      position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
      width: 520, maxHeight: '80vh', overflowY: 'auto', zIndex: 25,
      background: '#18181bf5', border: '2px solid #f59e0b44', borderRadius: 16,
      backdropFilter: 'blur(12px)', boxShadow: '0 0 60px rgba(245,158,11,0.1)',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: '#f59e0b08',
        position: 'sticky', top: 0, zIndex: 1,
      }}>
        <div>
          <div style={{ fontWeight: 800, fontSize: 15, color: '#f59e0b' }}>📋 中央广场公告板</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 2 }}>
            {data ? `最近 24 小时：${data.recent_conversations_24h} 次对话` : '加载中...'}
          </div>
        </div>
        <button onClick={() => setOpen(false)} style={{
          background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer',
        }}>✕</button>
      </div>

      {loading ? (
        <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>加载中...</div>
      ) : data && (
        <div style={{ padding: '16px 20px' }}>
          {/* Hot Residents */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#f59e0b', marginBottom: 10 }}>🔥 热门居民</div>
            {data.hot_residents.map((r, i) => (
              <div
                key={r.id}
                onClick={() => navigateTo(r)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                  cursor: 'pointer', borderRadius: 8, marginBottom: 4,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-input)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <span style={{
                  width: 22, height: 22, borderRadius: '50%', fontSize: 11, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: i < 3 ? '#f59e0b22' : 'var(--bg-input)',
                  color: i < 3 ? '#f59e0b' : 'var(--text-muted)',
                }}>{i + 1}</span>
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{r.name}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: 11, marginLeft: 6 }}>
                    {r.meta_json?.role ?? ''} · {DISTRICT_NAMES[r.district] ?? r.district}
                  </span>
                </div>
                <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>🔥 {r.heat}</span>
              </div>
            ))}
          </div>

          {/* New Residents */}
          <div>
            <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--accent-blue)', marginBottom: 10 }}>✨ 最新入住</div>
            {data.new_residents.map((r) => (
              <div
                key={r.id}
                onClick={() => navigateTo(r)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                  cursor: 'pointer', borderRadius: 8, marginBottom: 4,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-input)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{r.name}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: 11, marginLeft: 6 }}>
                    {r.meta_json?.role ?? ''} · {'⭐'.repeat(r.star_rating)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
