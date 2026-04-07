import { useEffect, useState } from 'react'
import { useGameStore } from '../../stores/gameStore'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface TxItem { id: string; amount: number; reason: string; created_at: string }

export function TransactionHistory() {
  const [transactions, setTransactions] = useState<TxItem[]>([])
  const [loading, setLoading] = useState(true)
  const token = useGameStore((s) => s.token)

  useEffect(() => {
    void (async () => {
      setLoading(true)
      try {
        const resp = await fetch(`${API}/profile/transactions`, { headers: { Authorization: `Bearer ${token ?? ''}` } })
        if (resp.ok) setTransactions(await resp.json())
      } catch { /* ignore */ } finally { setLoading(false) }
    })()
  }, [token])

  if (loading) return <div style={{ color: 'var(--text-muted)', padding: 20 }}>加载中...</div>

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20 }}>代币明细</h2>
      {transactions.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 40 }}>暂无代币记录</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {transactions.map((t) => (
            <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}>
              <span style={{ fontWeight: 700, fontSize: 14, color: t.amount > 0 ? 'var(--accent-green)' : 'var(--accent-red)', minWidth: 50 }}>{t.amount > 0 ? '+' : ''}{t.amount}</span>
              <span style={{ flex: 1, fontSize: 13, color: 'var(--text-secondary)' }}>{t.reason}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{new Date(t.created_at).toLocaleDateString('zh-CN')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
