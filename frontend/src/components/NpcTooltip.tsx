import { useEffect, useState } from 'react'
import { bridge } from '../game/phaserBridge'
import { STATUS_CONFIG } from '../game/StatusVisuals'
import { useGameStore } from '../stores/gameStore'
import type { ResidentData } from '../game/GameScene'

export function NpcTooltip() {
  const [npc, setNpc] = useState<ResidentData | null>(null)
  const chatOpen = useGameStore((s) => s.chatOpen)

  useEffect(() => {
    return bridge.on('npc:nearby', (data: unknown) => setNpc(data as ResidentData | null))
  }, [])

  if (!npc || chatOpen) return null

  const cfg = STATUS_CONFIG[npc.status] ?? STATUS_CONFIG.idle

  return (
    <div style={{
      position: 'fixed', top: 60, right: 12, zIndex: 15, minWidth: 180,
      background: '#18181bf5', color: '#d4d4d8', fontSize: 13,
      padding: '10px 14px', borderRadius: 10, border: '1px solid var(--border)',
      backdropFilter: 'blur(8px)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 22 }}>🧑‍💻</span>
        <div>
          <div style={{ color: '#fafafa', fontWeight: 700, fontSize: 14 }}>{npc.name}</div>
          <div style={{ color: '#71717a', fontSize: 12 }}>{npc.meta_json?.role ?? ''}</div>
        </div>
        <span style={{ marginLeft: 'auto', fontSize: 11 }}>{cfg.label}</span>
      </div>
      <div style={{ color: '#52525b', fontSize: 11, marginTop: 6, textAlign: 'center' }}>
        {cfg.canChat
          ? <span>按 <kbd style={{ background: '#27272a', padding: '1px 5px', borderRadius: 3, color: '#fafafa', fontSize: 10 }}>E</kbd> 开始对话</span>
          : npc.status === 'sleeping' ? '💤 正在沉睡，无法对话'
          : npc.status === 'chatting' ? '💬 正在和其他人聊天'
          : '暂时无法对话'}
      </div>
    </div>
  )
}
