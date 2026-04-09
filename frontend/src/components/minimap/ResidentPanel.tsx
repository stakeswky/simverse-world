import { useEffect, useState } from 'react'
import { bridge } from '../../game/phaserBridge'
import type { ResidentData } from '../../game/GameScene'
import { STATUS_CONFIG } from '../../game/StatusVisuals'
import { DISTRICTS, type DistrictKey } from './DistrictZones'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface Props {
  district: DistrictKey
  onClose: () => void
}

export function ResidentPanel({ district, onClose }: Props) {
  const [residents, setResidents] = useState<ResidentData[]>([])
  const config = DISTRICTS.find((d) => d.key === district)!

  useEffect(() => {
    fetch(`${API}/residents`)
      .then((r) => r.json())
      .then((all: ResidentData[]) => {
        setResidents(all.filter((r) => r.district === district))
      })
      .catch(() => setResidents([]))
  }, [district])

  const handleTeleport = (r: ResidentData) => {
    // Teleport to 1 tile left of the resident to avoid overlap
    bridge.emit('minimap:teleport', {
      tileX: r.tile_x - 1,
      tileY: r.tile_y,
      residentSlug: r.slug,
    })
    onClose()
  }

  return (
    <div style={{
      position: 'absolute',
      top: 0,
      left: 188, // 180px minimap + 8px gap
      width: 220,
      background: 'rgba(15,23,42,0.95)',
      border: `1px solid ${config.color.replace('0.8', '0.4')}`,
      borderRadius: 8,
      overflow: 'hidden',
      fontSize: 12,
      color: '#e2e8f0',
      zIndex: 20,
      boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 12px',
        background: config.bgColorDim,
        borderBottom: `1px solid ${config.color.replace('0.8', '0.3')}`,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ fontWeight: 'bold', color: config.color }}>
          {config.icon} {config.label}
        </span>
        <span
          onClick={onClose}
          style={{ fontSize: 10, color: '#64748b', cursor: 'pointer', padding: '0 4px' }}
        >✕</span>
      </div>

      {/* Resident list */}
      <div style={{ maxHeight: 200, overflowY: 'auto' }}>
        {residents.length === 0 && (
          <div style={{ padding: 16, textAlign: 'center', color: '#475569', fontSize: 11 }}>
            该街区暂无居民
          </div>
        )}
        {residents.map((r) => {
          const statusCfg = STATUS_CONFIG[r.status] ?? STATUS_CONFIG.idle
          const isSleeping = r.status === 'sleeping'
          return (
            <div
              key={r.slug}
              onClick={() => handleTeleport(r)}
              style={{
                padding: '8px 12px',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                borderBottom: '1px solid rgba(255,255,255,0.05)',
                cursor: 'pointer',
                opacity: isSleeping ? 0.5 : 1,
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = config.bgColorDim }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
            >
              <div style={{
                width: 28, height: 28,
                background: '#334155', borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 14, flexShrink: 0,
              }}>
                {statusCfg.bubble}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500, fontSize: 11, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {r.name}
                </div>
                <div style={{ fontSize: 9, color: '#64748b' }}>
                  {r.meta_json?.role || '居民'}
                </div>
              </div>
              <div style={{
                width: 6, height: 6,
                background: statusCfg.canChat ? '#22c55e' : '#94a3b8',
                borderRadius: '50%', flexShrink: 0,
              }} />
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div style={{
        padding: '6px 12px',
        background: 'rgba(0,0,0,0.3)',
        fontSize: 9,
        color: '#475569',
        textAlign: 'center',
      }}>
        点击居民传送到其身边
      </div>
    </div>
  )
}
