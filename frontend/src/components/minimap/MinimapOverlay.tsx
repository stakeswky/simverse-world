import { useState, useCallback, useEffect, useRef } from 'react'
import { MinimapCanvas } from './MinimapCanvas'
import { DistrictZones, type DistrictKey } from './DistrictZones'
import { ResidentPanel } from './ResidentPanel'
import { bridge } from '../../game/phaserBridge'

const MAP_TILES_W = 140
const MAP_TILES_H = 100
const SMALL_W = 180
const SMALL_H = 130
const LARGE_W = 560
const LARGE_H = 400

export function MinimapOverlay() {
  const [selectedDistrict, setSelectedDistrict] = useState<DistrictKey | null>(null)
  const [expanded, setExpanded] = useState(false)
  const smallMapRef = useRef<HTMLDivElement>(null)
  const largeMapRef = useRef<HTMLDivElement>(null)

  const handleSelectDistrict = useCallback((key: DistrictKey) => {
    setSelectedDistrict((prev) => (prev === key ? null : key))
  }, [])

  const handleClosePanel = useCallback(() => {
    setSelectedDistrict(null)
  }, [])

  const handleDoubleClick = useCallback(() => {
    setExpanded((prev) => !prev)
    setSelectedDistrict(null)
  }, [])

  // Convert click position to tile coordinates and teleport
  const handleMapClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    // Don't teleport if clicking a zone or resident — let those handlers take priority
    if (e.target !== e.currentTarget) return

    const container = e.currentTarget
    const rect = container.getBoundingClientRect()
    const clickX = e.clientX - rect.left
    const clickY = e.clientY - rect.top
    const mapW = container.clientWidth
    const mapH = container.clientHeight

    const tileX = Math.floor((clickX / mapW) * MAP_TILES_W)
    const tileY = Math.floor((clickY / mapH) * MAP_TILES_H)

    // Clamp to valid map bounds
    const clampedX = Math.max(0, Math.min(MAP_TILES_W - 1, tileX))
    const clampedY = Math.max(0, Math.min(MAP_TILES_H - 1, tileY))

    bridge.emit('minimap:teleport', { tileX: clampedX, tileY: clampedY })
  }, [])

  // ESC to close expanded minimap
  useEffect(() => {
    if (!expanded) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setExpanded(false)
        setSelectedDistrict(null)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [expanded])

  // Expanded: centered overlay with large map
  if (expanded) {
    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 50,
          background: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        onClick={(e) => {
          // Click backdrop to close panel (not collapse — use double-click to collapse)
          if (e.target === e.currentTarget) {
            setSelectedDistrict(null)
          }
        }}
      >
        <div style={{ position: 'relative' }}>
          {/* Large map container */}
          <div
            ref={largeMapRef}
            style={{
              width: LARGE_W,
              height: LARGE_H,
              background: 'rgba(0,0,0,0.85)',
              border: '1.5px solid rgba(255,255,255,0.25)',
              borderRadius: 12,
              overflow: 'hidden',
              boxShadow: '0 8px 40px rgba(0,0,0,0.7)',
              position: 'relative',
              cursor: 'pointer',
            }}
            onClick={(e) => {
              // Click on empty map area → teleport
              if (e.target === e.currentTarget) {
                handleMapClick(e)
              } else {
                // Click on zone or other element → clear panel
                setSelectedDistrict(null)
              }
            }}
            onDoubleClick={handleDoubleClick}
          >
            <MinimapCanvas width={LARGE_W} height={LARGE_H} />
            <DistrictZones
              selected={selectedDistrict}
              onSelect={handleSelectDistrict}
              mapWidth={LARGE_W}
              mapHeight={LARGE_H}
            />
          </div>

          {/* Resident panel to the right of the large map */}
          {selectedDistrict && (
            <ResidentPanel
              district={selectedDistrict}
              onClose={handleClosePanel}
              panelLeft={LARGE_W + 8}
            />
          )}
        </div>
      </div>
    )
  }

  // Collapsed: small minimap in top-left
  return (
    <div
      style={{
        position: 'fixed',
        top: 52,
        left: 12,
        zIndex: 15,
      }}
    >
      {/* Small map container */}
      <div
        ref={smallMapRef}
        style={{
          width: SMALL_W,
          height: SMALL_H,
          background: 'rgba(0,0,0,0.7)',
          border: '1.5px solid rgba(255,255,255,0.2)',
          borderRadius: 8,
          overflow: 'hidden',
          boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
          position: 'relative',
          cursor: 'pointer',
        }}
        onClick={(e) => {
          // Click on empty map area → teleport
          if (e.target === e.currentTarget) {
            handleMapClick(e)
          } else {
            // Click on zone → clear any open panel from previous selection
            setSelectedDistrict(null)
          }
        }}
        onDoubleClick={handleDoubleClick}
      >
        <MinimapCanvas />
        <DistrictZones selected={selectedDistrict} onSelect={handleSelectDistrict} />
      </div>

      {/* Resident panel */}
      {selectedDistrict && (
        <ResidentPanel district={selectedDistrict} onClose={handleClosePanel} />
      )}
    </div>
  )
}
