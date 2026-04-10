import { useEffect, useRef, useState } from 'react'

interface SbtiInfo {
  type: string
  type_name: string
}

interface ResidentCardProps {
  resident: {
    id: string
    slug: string
    name: string
    star_rating: number
    status: string
    heat: number
    district: string
    total_conversations: number
    avg_rating: number
    sprite_key: string
    meta_json: { role?: string; sbti?: SbtiInfo } | null
  }
  onEdit: (slug: string) => void
  /** Optional: pass the latest WS message so ResidentCard can react to type changes */
  lastWsMessage?: { type: string; resident_id: string; new_type: string; type_name: string } | null
}

const STATUS_LABELS: Record<string, string> = {
  idle: '🟢 空闲',
  chatting: '💬 对话中',
  sleeping: '💤 沉睡',
  popular: '🔥 热门',
}

export function ResidentCard({ resident, onEdit, lastWsMessage }: ResidentCardProps) {
  const [isFlashing, setIsFlashing] = useState(false)
  const [displayedType, setDisplayedType] = useState<SbtiInfo | undefined>(
    resident.meta_json?.sbti ?? undefined
  )
  const flashTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // React to resident_type_changed WS messages
  useEffect(() => {
    if (
      lastWsMessage?.type === 'resident_type_changed' &&
      lastWsMessage.resident_id === resident.id
    ) {
      setDisplayedType({ type: lastWsMessage.new_type, type_name: lastWsMessage.type_name })
      setIsFlashing(true)

      if (flashTimeoutRef.current) {
        clearTimeout(flashTimeoutRef.current)
      }
      flashTimeoutRef.current = setTimeout(() => {
        setIsFlashing(false)
      }, 1500)
    }
  }, [lastWsMessage, resident.id])

  // Sync displayed type with prop updates (e.g. after page reload)
  useEffect(() => {
    if (resident.meta_json?.sbti) {
      setDisplayedType(resident.meta_json.sbti)
    }
  }, [resident.meta_json?.sbti?.type])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current)
    }
  }, [])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px',
      background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 12,
    }}>
      <div style={{
        width: 48, height: 48, background: 'var(--bg-input)', borderRadius: 8,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 24, flexShrink: 0,
      }}>🧑‍💻</div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>{resident.name}</span>
          <span style={{ fontSize: 12 }}>{'⭐'.repeat(resident.star_rating)}</span>
          {displayedType && (
            <span
              style={{
                fontSize: 10,
                padding: '1px 6px',
                borderRadius: 4,
                background: isFlashing ? 'var(--accent-alt, #fd79a8)' : 'var(--accent, #6c5ce7)',
                color: '#fff',
                fontWeight: 600,
                letterSpacing: 0.5,
                transition: 'background 0.3s ease',
                transform: isFlashing ? 'scale(1.15)' : 'scale(1)',
                display: 'inline-block',
              }}
              title={displayedType.type_name}
            >
              {displayedType.type}
            </span>
          )}
        </div>

        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 2 }}>
          {resident.meta_json?.role ?? ''} · {resident.district}
        </div>

        <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}>
          <span>{STATUS_LABELS[resident.status] ?? resident.status}</span>
          <span>🔥 {resident.heat}</span>
          <span>💬 {resident.total_conversations}</span>
          {resident.avg_rating > 0 && <span>⭐ {resident.avg_rating.toFixed(1)}</span>}
        </div>
      </div>

      <button
        onClick={() => onEdit(resident.slug)}
        style={{
          background: 'var(--bg-input)', border: '1px solid var(--border)',
          color: 'var(--text-secondary)', padding: '6px 14px', borderRadius: 6,
          fontSize: 12, cursor: 'pointer', flexShrink: 0,
        }}
      >
        编辑
      </button>
    </div>
  )
}
