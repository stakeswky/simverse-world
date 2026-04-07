import { useEffect, useState } from 'react'
import { useGameStore } from '../../stores/gameStore'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface ConvItem {
  id: string; resident_name: string; resident_slug: string;
  started_at: string; ended_at: string | null; turns: number; rating: number | null;
}

export function ConversationHistory() {
  const [conversations, setConversations] = useState<ConvItem[]>([])
  const [loading, setLoading] = useState(true)
  const token = useGameStore((s) => s.token)

  useEffect(() => {
    void (async () => {
      setLoading(true)
      try {
        const resp = await fetch(`${API}/profile/conversations`, { headers: { Authorization: `Bearer ${token ?? ''}` } })
        if (resp.ok) setConversations(await resp.json())
      } catch { /* ignore */ } finally { setLoading(false) }
    })()
  }, [token])

  if (loading) return <div style={{ color: 'var(--text-muted)', padding: 20 }}>加载中...</div>

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20 }}>对话历史</h2>
      {conversations.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 40 }}>暂无对话记录</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {conversations.map((c) => (
            <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{c.resident_name}</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 2 }}>
                  {new Date(c.started_at).toLocaleDateString('zh-CN')} · {c.turns} 轮对话
                </div>
              </div>
              {c.rating != null && <span style={{ fontSize: 12 }}>{'⭐'.repeat(c.rating)}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
