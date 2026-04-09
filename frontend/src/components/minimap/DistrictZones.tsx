const MAP_TILES_W = 140
const MAP_TILES_H = 100

export type DistrictKey = 'engineering' | 'product' | 'academy' | 'free'

export interface DistrictConfig {
  key: DistrictKey
  label: string
  icon: string
  color: string        // border + highlight color
  bgColor: string      // normal background
  bgColorDim: string   // dimmed when another district is selected
  tileRect: { x: number; y: number; w: number; h: number } // tile bounds
}

export const DISTRICTS: DistrictConfig[] = [
  {
    key: 'engineering', label: '工程区', icon: '⚙️',
    color: 'rgba(59,130,246,0.8)', bgColor: 'rgba(59,130,246,0.35)', bgColorDim: 'rgba(59,130,246,0.12)',
    tileRect: { x: 54, y: 53, w: 12, h: 12 },
  },
  {
    key: 'product', label: '产品区', icon: '📦',
    color: 'rgba(168,85,247,0.8)', bgColor: 'rgba(168,85,247,0.35)', bgColorDim: 'rgba(168,85,247,0.12)',
    tileRect: { x: 33, y: 38, w: 8, h: 16 },
  },
  {
    key: 'academy', label: '学院区', icon: '🎓',
    color: 'rgba(34,197,94,0.8)', bgColor: 'rgba(34,197,94,0.35)', bgColorDim: 'rgba(34,197,94,0.12)',
    tileRect: { x: 28, y: 63, w: 8, h: 16 },
  },
  {
    key: 'free', label: '自由区', icon: '🆓',
    color: 'rgba(251,191,36,0.8)', bgColor: 'rgba(251,191,36,0.35)', bgColorDim: 'rgba(251,191,36,0.12)',
    tileRect: { x: 98, y: 36, w: 12, h: 10 },
  },
]

function tileToMinimap(tileX: number, tileY: number, tileW: number, tileH: number, mapW: number, mapH: number) {
  return {
    left: (tileX / MAP_TILES_W) * mapW,
    top: (tileY / MAP_TILES_H) * mapH,
    width: (tileW / MAP_TILES_W) * mapW,
    height: (tileH / MAP_TILES_H) * mapH,
  }
}

interface Props {
  selected: DistrictKey | null
  onSelect: (key: DistrictKey) => void
  mapWidth?: number
  mapHeight?: number
}

export function DistrictZones({ selected, onSelect, mapWidth = 180, mapHeight = 130 }: Props) {
  const expanded = mapWidth > 200
  return (
    <>
      {DISTRICTS.map((d) => {
        const pos = tileToMinimap(d.tileRect.x, d.tileRect.y, d.tileRect.w, d.tileRect.h, mapWidth, mapHeight)
        const isSelected = selected === d.key
        const isDimmed = selected !== null && !isSelected

        return (
          <div
            key={d.key}
            onClick={(e) => { e.stopPropagation(); onSelect(d.key) }}
            title={d.label}
            style={{
              position: 'absolute',
              left: pos.left,
              top: pos.top,
              width: pos.width,
              height: pos.height,
              background: isDimmed ? d.bgColorDim : d.bgColor,
              border: isSelected ? `2px solid ${d.color}` : `1px solid ${d.color.replace('0.8', '0.4')}`,
              borderRadius: 3,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: expanded ? 16 : 8,
              transition: 'all 0.15s ease',
              boxShadow: isSelected ? `0 0 8px ${d.color}` : 'none',
            }}
          >
            {d.icon}
          </div>
        )
      })}
    </>
  )
}
