import { useEffect, useState } from 'react'
import MDEditor from '@uiw/react-md-editor'
import { useGameStore } from '../../stores/gameStore'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

type Layer = 'ability' | 'persona' | 'soul'

interface ResidentDetail {
  slug: string
  name: string
  ability_md: string
  persona_md: string
  soul_md: string
  star_rating: number
  total_conversations: number
  avg_rating: number
  meta_json: { role?: string } | null
}

interface VersionSnapshot {
  version_number: number
  ability_md: string
  persona_md: string
  soul_md: string
  created_at: string
}

interface ResidentEditorProps {
  slug: string
  onBack: () => void
}

const LAYER_CONFIG: { key: Layer; icon: string; label: string; description: string }[] = [
  { key: 'ability', icon: '📋', label: 'Ability', description: '能力层 — 这个人能做什么' },
  { key: 'persona', icon: '🎭', label: 'Persona', description: '人格层 — 怎么做、怎么说' },
  { key: 'soul', icon: '💎', label: 'Soul', description: '灵魂层 — 为什么这样做' },
]

export function ResidentEditor({ slug, onBack }: ResidentEditorProps) {
  const token = useGameStore((s) => s.token)
  const [resident, setResident] = useState<ResidentDetail | null>(null)
  const [activeLayer, setActiveLayer] = useState<Layer>('ability')
  const [drafts, setDrafts] = useState<Record<Layer, string>>({ ability: '', persona: '', soul: '' })
  const [versions, setVersions] = useState<VersionSnapshot[]>([])
  const [showVersions, setShowVersions] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const headers = { Authorization: `Bearer ${token ?? ''}` }
        const [resResp, verResp] = await Promise.all([
          fetch(`${API}/residents/${slug}`, { headers }),
          fetch(`${API}/residents/${slug}/versions`, { headers }),
        ])
        if (resResp.ok) {
          const data: ResidentDetail = await resResp.json()
          setResident(data)
          setDrafts({ ability: data.ability_md, persona: data.persona_md, soul: data.soul_md })
        }
        if (verResp.ok) setVersions(await verResp.json())
      } catch { /* ignore */ }
      finally { setLoading(false) }
    }
    void fetchData()
  }, [slug, token])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const resp = await fetch(`${API}/residents/${slug}`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token ?? ''}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ ability_md: drafts.ability, persona_md: drafts.persona, soul_md: drafts.soul }),
      })
      if (resp.ok) {
        const updated: ResidentDetail = await resp.json()
        setResident(updated)
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
        const verResp = await fetch(`${API}/residents/${slug}/versions`, {
          headers: { Authorization: `Bearer ${token ?? ''}` },
        })
        if (verResp.ok) setVersions(await verResp.json())
      }
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  const restoreVersion = (v: VersionSnapshot) => {
    setDrafts({ ability: v.ability_md, persona: v.persona_md, soul: v.soul_md })
    setShowVersions(false)
  }

  if (loading) return <div style={{ color: 'var(--text-muted)', padding: 40, textAlign: 'center' }}>加载中...</div>
  if (!resident) return <div style={{ color: 'var(--accent-red)', padding: 40, textAlign: 'center' }}>找不到居民</div>

  return (
    <div style={{ display: 'flex', minHeight: 'calc(100vh - var(--nav-height))' }}>
      <div style={{ flex: 1, padding: '24px 32px', maxWidth: 900 }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <button onClick={onBack} style={{
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            color: 'var(--text-secondary)', padding: '6px 12px', borderRadius: 6,
            fontSize: 13, cursor: 'pointer',
          }}>← 返回</button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 18 }}>{resident.name}</div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              {'⭐'.repeat(resident.star_rating)} · {resident.meta_json?.role ?? ''} ·
              💬 {resident.total_conversations} · ⭐ {resident.avg_rating.toFixed(1)}
            </div>
          </div>
          <button onClick={() => setShowVersions(!showVersions)} style={{
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            color: 'var(--text-secondary)', padding: '6px 14px', borderRadius: 6,
            fontSize: 12, cursor: 'pointer',
          }}>📜 历史版本 ({versions.length})</button>
          <button onClick={() => void handleSave()} disabled={saving} style={{
            background: saved ? 'var(--accent-green)' : 'var(--accent-red)',
            color: 'white', border: 'none', padding: '8px 20px', borderRadius: 6,
            fontSize: 13, fontWeight: 600, cursor: saving ? 'default' : 'pointer',
            transition: 'background 0.2s ease',
          }}>{saving ? '保存中...' : saved ? '已保存!' : '保存'}</button>
        </div>

        {/* Layer tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
          {LAYER_CONFIG.map((layer) => (
            <button key={layer.key} onClick={() => setActiveLayer(layer.key)} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', borderRadius: '8px 8px 0 0',
              background: activeLayer === layer.key ? 'var(--bg-card)' : 'transparent',
              border: activeLayer === layer.key ? '1px solid var(--border)' : '1px solid transparent',
              borderBottom: activeLayer === layer.key ? '1px solid var(--bg-card)' : '1px solid var(--border)',
              color: activeLayer === layer.key ? 'var(--text-primary)' : 'var(--text-muted)',
              fontSize: 13, fontWeight: activeLayer === layer.key ? 600 : 400, cursor: 'pointer',
            }}>{layer.icon} {layer.label}</button>
          ))}
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 12 }}>
          {LAYER_CONFIG.find((l) => l.key === activeLayer)?.description}
        </div>

        {/* Markdown editor */}
        <div data-color-mode="dark">
          <MDEditor
            value={drafts[activeLayer]}
            onChange={(val) => setDrafts((prev) => ({ ...prev, [activeLayer]: val ?? '' }))}
            height={500}
            preview="live"
          />
        </div>
      </div>

      {/* Version history panel */}
      {showVersions && (
        <div style={{
          width: 300, borderLeft: '1px solid var(--border)',
          background: 'var(--bg-card)', padding: '24px 16px', overflowY: 'auto',
        }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>历史版本</h3>
          {versions.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>暂无历史版本</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {versions.map((v) => (
                <div key={v.version_number} onClick={() => restoreVersion(v)} style={{
                  padding: '10px 12px', background: 'var(--bg-input)', borderRadius: 8,
                  cursor: 'pointer', border: '1px solid var(--border)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>v{v.version_number}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                      {new Date(v.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
                    </span>
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 4 }}>点击恢复此版本</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
