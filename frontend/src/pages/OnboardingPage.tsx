import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGameStore } from '../stores/gameStore'
import {
  checkOnboarding,
  getResidents,
  getSpriteTemplates,
  loadPreset,
  skipOnboarding,
} from '../services/api'
import type { ResidentListItem, SpriteTemplate } from '../services/api'

interface PresetCard {
  slug: string
  name: string
  district: string
  sprite_key: string
  star_rating: number
  vibe?: string
  tags?: string[]
}

const DISTRICT_LABELS: Record<string, string> = {
  engineering: '工程区',
  product: '产品区',
  academy: '学术区',
  free: '自由区',
}

function districtLabel(district: string): string {
  return DISTRICT_LABELS[district] ?? district
}

function districtColor(district: string): string {
  const map: Record<string, string> = {
    engineering: '#0ea5e9',
    product: '#a855f7',
    academy: '#f59e0b',
    free: '#53d769',
  }
  return map[district] ?? '#71717a'
}

export function OnboardingPage() {
  const navigate = useNavigate()
  const token = useGameStore((s) => s.token)

  const [presets, setPresets] = useState<PresetCard[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      navigate('/login', { replace: true })
      return
    }

    let cancelled = false

    async function init() {
      setLoading(true)
      try {
        // Check if onboarding is needed
        const check = await checkOnboarding(token!)
        if (!check.needs_onboarding) {
          navigate('/', { replace: true })
          return
        }

        // Fetch residents and sprite templates in parallel
        const [residents, templates] = await Promise.all([
          getResidents(),
          getSpriteTemplates(),
        ])

        if (cancelled) return

        // Build a lookup from sprite_key → template attributes
        const templateMap = new Map<string, SpriteTemplate>(
          templates.map((t) => [t.key, t])
        )

        // Filter residents that are marked as presets (meta_json.origin === 'preset')
        const presetResidents: ResidentListItem[] = residents.filter(
          (r) => r.meta_json?.origin === 'preset'
        )

        const cards: PresetCard[] = presetResidents.map((r) => {
          const tmpl = templateMap.get(r.sprite_key)
          return {
            slug: r.slug,
            name: r.name,
            district: r.district,
            sprite_key: r.sprite_key,
            star_rating: r.star_rating,
            vibe: tmpl?.vibe,
            tags: tmpl?.tags,
          }
        })

        setPresets(cards)
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载失败，请刷新重试')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    init()
    return () => { cancelled = true }
  }, [token, navigate])

  async function handleSelectPreset(slug: string) {
    if (!token || actionLoading) return
    setSelected(slug)
    setActionLoading(true)
    setError('')
    try {
      await loadPreset(token, slug)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '选择失败，请重试')
      setSelected(null)
      setActionLoading(false)
    }
  }

  async function handleSkip() {
    if (!token || actionLoading) return
    setActionLoading(true)
    setError('')
    try {
      await skipOnboarding(token)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败，请重试')
      setActionLoading(false)
    }
  }

  return (
    <div style={{
      height: '100vh',
      background: 'linear-gradient(135deg, #0f0f17 0%, #1a1a2e 50%, #0f3460 100%)',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '40px 20px 80px',
      boxSizing: 'border-box',
    }}>
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: 36, maxWidth: 600 }}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>🏙️</div>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-primary)', marginBottom: 8 }}>
          欢迎来到 Skills World
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.6 }}>
          选择一个预设角色开始你的城市生活，或跳过使用默认角色
        </p>
      </div>

      {/* Loading state */}
      {loading && (
        <div style={{ color: 'var(--text-muted)', fontSize: 14, marginTop: 40 }}>
          正在加载角色列表…
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          color: 'var(--accent-red)',
          background: '#e9456015',
          border: '1px solid #e9456030',
          borderRadius: 8,
          padding: '10px 16px',
          fontSize: 13,
          marginBottom: 20,
          maxWidth: 600,
          width: '100%',
          textAlign: 'center',
        }}>
          {error}
        </div>
      )}

      {/* Preset grid */}
      {!loading && presets.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
          gap: 16,
          width: '100%',
          maxWidth: 900,
        }}>
          {presets.map((card) => (
            <PresetCardItem
              key={card.slug}
              card={card}
              isSelected={selected === card.slug}
              disabled={actionLoading}
              onSelect={handleSelectPreset}
            />
          ))}
        </div>
      )}

      {/* No presets fallback */}
      {!loading && presets.length === 0 && !error && (
        <div style={{
          color: 'var(--text-muted)',
          fontSize: 15,
          marginTop: 40,
          textAlign: 'center',
          lineHeight: 2,
        }}>
          暂无预设角色
          <br />
          <span style={{ fontSize: 13 }}>请点击下方按钮使用默认角色进入游戏</span>
        </div>
      )}

      {/* Skip button */}
      {!loading && (
        <div style={{ marginTop: 36, textAlign: 'center' }}>
          <button
            onClick={handleSkip}
            disabled={actionLoading}
            style={{
              background: 'transparent',
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
              padding: '10px 28px',
              borderRadius: 'var(--radius)',
              fontSize: 13,
              cursor: actionLoading ? 'not-allowed' : 'pointer',
              opacity: actionLoading ? 0.5 : 1,
              transition: 'all 0.15s',
            }}
            onMouseEnter={(e) => {
              if (!actionLoading) {
                ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'
                ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--text-muted)'
              }
            }}
            onMouseLeave={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)'
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)'
            }}
          >
            跳过，使用默认角色
          </button>
        </div>
      )}
    </div>
  )
}

interface PresetCardItemProps {
  card: PresetCard
  isSelected: boolean
  disabled: boolean
  onSelect: (slug: string) => void
}

function PresetCardItem({ card, isSelected, disabled, onSelect }: PresetCardItemProps) {
  const [hovered, setHovered] = useState(false)
  const [imgError, setImgError] = useState(false)

  const borderColor = isSelected
    ? 'var(--accent-red)'
    : hovered
    ? '#3f3f46'
    : 'var(--border)'

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: `1px solid ${borderColor}`,
        borderRadius: 12,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled && !isSelected ? 0.6 : 1,
        transition: 'border-color 0.15s, transform 0.15s',
        transform: hovered && !disabled ? 'translateY(-2px)' : 'none',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Sprite preview */}
      <div style={{
        width: '100%',
        aspectRatio: '1',
        borderRadius: 8,
        background: 'var(--bg-input)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        position: 'relative',
      }}>
        {!imgError ? (
          <img
            src={`/assets/village/agents/${encodeURIComponent(card.sprite_key)}/texture.png`}
            alt={card.name}
            onError={() => setImgError(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              imageRendering: 'pixelated',
            }}
          />
        ) : (
          <div style={{ fontSize: 32, color: 'var(--text-muted)' }}>👤</div>
        )}
      </div>

      {/* Name + district */}
      <div>
        <div style={{
          fontWeight: 700,
          fontSize: 15,
          color: 'var(--text-primary)',
          marginBottom: 4,
        }}>
          {card.name}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={{
            background: districtColor(card.district) + '20',
            color: districtColor(card.district),
            border: `1px solid ${districtColor(card.district)}40`,
            borderRadius: 4,
            padding: '1px 6px',
            fontSize: 11,
            fontWeight: 600,
          }}>
            {districtLabel(card.district)}
          </span>
          {card.star_rating > 0 && (
            <span style={{ fontSize: 11, color: '#f59e0b' }}>
              {'★'.repeat(Math.min(card.star_rating, 5))}
            </span>
          )}
        </div>
      </div>

      {/* Vibe / tags */}
      {(card.vibe || (card.tags && card.tags.length > 0)) && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          {card.vibe && <span style={{ marginRight: 4 }}>#{card.vibe}</span>}
          {card.tags?.slice(0, 2).map((tag) => (
            <span key={tag} style={{ marginRight: 4 }}>#{tag}</span>
          ))}
        </div>
      )}

      {/* Select button */}
      <button
        onClick={() => !disabled && onSelect(card.slug)}
        disabled={disabled}
        style={{
          marginTop: 'auto',
          width: '100%',
          background: isSelected ? 'var(--accent-red)' : hovered ? '#e9456022' : 'transparent',
          border: `1px solid ${isSelected ? 'var(--accent-red)' : 'var(--border)'}`,
          color: isSelected ? 'white' : hovered ? 'var(--accent-red)' : 'var(--text-secondary)',
          padding: '7px 0',
          borderRadius: 'var(--radius)',
          fontSize: 13,
          fontWeight: 600,
          cursor: disabled ? 'not-allowed' : 'pointer',
          transition: 'all 0.15s',
        }}
      >
        {isSelected ? '选择中…' : '选择此角色'}
      </button>
    </div>
  )
}
