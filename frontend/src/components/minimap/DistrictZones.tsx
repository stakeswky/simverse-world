const MAP_TILES_W = 140
const MAP_TILES_H = 100

export type LocationKey =
  | 'academy' | 'tavern' | 'cafe' | 'workshop'
  | 'library' | 'shop' | 'town_hall'
  | 'north_path' | 'central_plaza' | 'south_lawn' | 'town_entrance'

export interface LocationConfig {
  key: LocationKey
  label: string
  icon: string
  color: string
  bgColor: string
  bgColorDim: string
  tileRect: { x: number; y: number; w: number; h: number }
}

export const LOCATIONS: LocationConfig[] = [
  // Public facilities — colored
  {
    key: 'academy', label: '学院', icon: '🏫',
    color: 'rgba(34,197,94,0.8)', bgColor: 'rgba(34,197,94,0.35)', bgColorDim: 'rgba(34,197,94,0.12)',
    tileRect: { x: 25, y: 18, w: 17, h: 16 },
  },
  {
    key: 'tavern', label: '酒馆', icon: '🍺',
    color: 'rgba(239,68,68,0.8)', bgColor: 'rgba(239,68,68,0.35)', bgColorDim: 'rgba(239,68,68,0.12)',
    tileRect: { x: 72, y: 13, w: 11, h: 13 },
  },
  {
    key: 'cafe', label: '咖啡馆', icon: '☕',
    color: 'rgba(245,158,11,0.8)', bgColor: 'rgba(245,158,11,0.35)', bgColorDim: 'rgba(245,158,11,0.12)',
    tileRect: { x: 53, y: 14, w: 9, h: 12 },
  },
  {
    key: 'workshop', label: '工坊', icon: '🔨',
    color: 'rgba(168,85,247,0.8)', bgColor: 'rgba(168,85,247,0.35)', bgColorDim: 'rgba(168,85,247,0.12)',
    tileRect: { x: 108, y: 20, w: 16, h: 14 },
  },
  {
    key: 'library', label: '图书馆', icon: '📚',
    color: 'rgba(59,130,246,0.8)', bgColor: 'rgba(59,130,246,0.35)', bgColorDim: 'rgba(59,130,246,0.12)',
    tileRect: { x: 57, y: 43, w: 13, h: 10 },
  },
  {
    key: 'shop', label: '杂货铺', icon: '🏪',
    color: 'rgba(236,72,153,0.8)', bgColor: 'rgba(236,72,153,0.35)', bgColorDim: 'rgba(236,72,153,0.12)',
    tileRect: { x: 75, y: 43, w: 18, h: 10 },
  },
  {
    key: 'town_hall', label: '市政厅', icon: '🏛',
    color: 'rgba(14,165,233,0.8)', bgColor: 'rgba(14,165,233,0.35)', bgColorDim: 'rgba(14,165,233,0.12)',
    tileRect: { x: 106, y: 45, w: 26, h: 17 },
  },
  // Outdoor areas — neutral
  {
    key: 'north_path', label: '北林荫道', icon: '🌳',
    color: 'rgba(100,116,139,0.6)', bgColor: 'rgba(100,116,139,0.2)', bgColorDim: 'rgba(100,116,139,0.08)',
    tileRect: { x: 15, y: 35, w: 120, h: 7 },
  },
  {
    key: 'central_plaza', label: '中央广场', icon: '🏠',
    color: 'rgba(100,116,139,0.6)', bgColor: 'rgba(100,116,139,0.2)', bgColorDim: 'rgba(100,116,139,0.08)',
    tileRect: { x: 55, y: 54, w: 40, h: 4 },
  },
  {
    key: 'south_lawn', label: '南草坪', icon: '🌿',
    color: 'rgba(100,116,139,0.6)', bgColor: 'rgba(100,116,139,0.2)', bgColorDim: 'rgba(100,116,139,0.08)',
    tileRect: { x: 15, y: 76, w: 84, h: 7 },
  },
  {
    key: 'town_entrance', label: '小镇入口', icon: '🚪',
    color: 'rgba(100,116,139,0.6)', bgColor: 'rgba(100,116,139,0.2)', bgColorDim: 'rgba(100,116,139,0.08)',
    tileRect: { x: 50, y: 85, w: 40, h: 14 },
  },
]

// Backwards-compatible alias for existing imports
export type DistrictKey = LocationKey
export const DISTRICTS = LOCATIONS

function tileToMinimap(tileX: number, tileY: number, tileW: number, tileH: number, mapW: number, mapH: number) {
  return {
    left: (tileX / MAP_TILES_W) * mapW,
    top: (tileY / MAP_TILES_H) * mapH,
    width: (tileW / MAP_TILES_W) * mapW,
    height: (tileH / MAP_TILES_H) * mapH,
  }
}

interface Props {
  selected: LocationKey | null
  onSelect: (key: LocationKey) => void
  mapWidth?: number
  mapHeight?: number
}

export function DistrictZones({ selected, onSelect, mapWidth = 180, mapHeight = 130 }: Props) {
  const expanded = mapWidth > 200
  return (
    <>
      {LOCATIONS.map((d) => {
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
              border: isSelected ? `2px solid ${d.color}` : `1px solid ${d.color.replace('0.8', '0.4').replace('0.6', '0.3')}`,
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
