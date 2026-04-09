import { useState, useCallback } from 'react'
import { MinimapCanvas } from './MinimapCanvas'
import { DistrictZones, type DistrictKey } from './DistrictZones'
import { ResidentPanel } from './ResidentPanel'

export function MinimapOverlay() {
  const [selectedDistrict, setSelectedDistrict] = useState<DistrictKey | null>(null)

  const handleSelectDistrict = useCallback((key: DistrictKey) => {
    setSelectedDistrict((prev) => (prev === key ? null : key))
  }, [])

  const handleClosePanel = useCallback(() => {
    setSelectedDistrict(null)
  }, [])

  return (
    <div
      style={{
        position: 'fixed',
        top: 52,
        left: 12,
        zIndex: 15,
      }}
      onClick={(e) => {
        // Close panel when clicking the minimap background (not a zone)
        if (e.target === e.currentTarget) {
          setSelectedDistrict(null)
        }
      }}
    >
      {/* Minimap container */}
      <div style={{
        width: 180,
        height: 130,
        background: 'rgba(0,0,0,0.7)',
        border: '1.5px solid rgba(255,255,255,0.2)',
        borderRadius: 8,
        overflow: 'hidden',
        boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
        position: 'relative',
      }}>
        <MinimapCanvas />
        <DistrictZones selected={selectedDistrict} onSelect={handleSelectDistrict} />
      </div>

      {/* Resident panel (conditionally rendered) */}
      {selectedDistrict && (
        <ResidentPanel district={selectedDistrict} onClose={handleClosePanel} />
      )}
    </div>
  )
}
