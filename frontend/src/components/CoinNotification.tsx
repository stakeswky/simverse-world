import { useState, useEffect, useCallback, useRef } from 'react'
import { onWSMessage } from '../services/ws'

interface CoinNotif {
  id: number
  amount: number
  reason: string
}

let notifCounter = 0

const REASON_LABELS: Record<string, string> = {
  daily_login_reward: '每日奖励',
  creator_passive: '创作者收益',
  skill_creation: 'Skill 炼化',
  chat: '对话',
  signup_bonus: '新手礼包',
  good_rating: '好评奖励',
}

export function CoinNotification() {
  const [notifications, setNotifications] = useState<CoinNotif[]>([])
  const timersRef = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const add = useCallback((amount: number, reason: string) => {
    const id = ++notifCounter
    setNotifications((prev) => [...prev, { id, amount, reason }])
    const t = setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== id))
      timersRef.current.delete(id)
    }, 3000)
    timersRef.current.set(id, t)
  }, [])

  useEffect(() => {
    const unsub = onWSMessage((data) => {
      if (data.type === 'coin_earned' && typeof data.amount === 'number') {
        add(data.amount as number, (data.reason as string) || 'coin_earned')
      }
      if (data.type === 'daily_reward' && typeof data.amount === 'number') {
        add(data.amount as number, 'daily_login_reward')
      }
      if (data.type === 'coin_update' && typeof data.delta === 'number' && (data.delta as number) < 0) {
        add(data.delta as number, (data.reason as string) || 'chat')
      }
    })
    return unsub
  }, [add])

  useEffect(() => () => { timersRef.current.forEach(clearTimeout) }, [])

  if (notifications.length === 0) return null

  return (
    <div style={{
      position: 'fixed', top: 56, left: '50%', transform: 'translateX(-50%)',
      zIndex: 30, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
      pointerEvents: 'none',
    }}>
      {notifications.map((n) => (
        <div key={n.id} style={{
          padding: '8px 18px', borderRadius: 20, fontSize: 14, fontWeight: 700,
          animation: 'coinFloatUp 3s ease-out forwards',
          background: n.amount > 0 ? '#53d76920' : '#e9456020',
          color: n.amount > 0 ? '#53d769' : '#e94560',
          border: `1px solid ${n.amount > 0 ? '#53d76940' : '#e9456040'}`,
          backdropFilter: 'blur(8px)',
          whiteSpace: 'nowrap',
        }}>
          🪙 {n.amount > 0 ? '+' : ''}{n.amount}
          <span style={{ color: 'var(--text-muted)', fontSize: 11, marginLeft: 8 }}>
            {REASON_LABELS[n.reason] ?? n.reason}
          </span>
        </div>
      ))}
    </div>
  )
}
