import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGameStore } from '../../stores/gameStore'
import { ResidentCard } from './ResidentCard'
import { importSkill } from '../../services/api'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface ResidentItem {
  id: string; slug: string; name: string; star_rating: number; status: string;
  heat: number; district: string; total_conversations: number; avg_rating: number;
  sprite_key: string; meta_json: { role?: string } | null;
}

function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, '-')
    .replace(/^-|-$/g, '')
    || `skill-${Date.now()}`
}

interface ImportModalProps {
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

function ImportModal({ open, onClose, onSuccess }: ImportModalProps) {
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const reset = useCallback(() => {
    setFile(null)
    setName('')
    setSlug('')
    setUploading(false)
    setError(null)
    setSuccess(false)
    setDragOver(false)
  }, [])

  const handleClose = useCallback(() => {
    reset()
    onClose()
  }, [reset, onClose])

  const handleFile = useCallback((f: File) => {
    const ext = f.name.toLowerCase()
    if (!ext.endsWith('.md') && !ext.endsWith('.txt') && !ext.endsWith('.zip')) {
      setError('不支持的文件格式，请使用 .md 或 .zip 文件')
      return
    }
    setFile(f)
    setError(null)
    if (!name) {
      const baseName = f.name.replace(/\.(md|txt|zip)$/i, '')
      setName(baseName)
      setSlug(generateSlug(baseName))
    }
  }, [name])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile) handleFile(droppedFile)
  }, [handleFile])

  const handleSubmit = useCallback(async () => {
    if (!file || !name.trim() || !slug.trim()) return
    setUploading(true)
    setError(null)
    try {
      await importSkill(file, name.trim(), slug.trim())
      setSuccess(true)
      setTimeout(() => {
        onSuccess()
        handleClose()
      }, 1200)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '导入失败'
      setError(msg)
    } finally {
      setUploading(false)
    }
  }, [file, name, slug, onSuccess, handleClose])

  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={handleClose}
    >
      <div
        style={{
          background: '#18181b', border: '1px solid #27272a', borderRadius: 12,
          padding: 28, width: 480, maxWidth: '90vw', maxHeight: '90vh', overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>导入 Skill</h3>
          <button
            onClick={handleClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer', padding: 4 }}
          >
            x
          </button>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: `2px dashed ${dragOver ? '#e94560' : '#27272a'}`,
            borderRadius: 8, padding: 32, textAlign: 'center', cursor: 'pointer',
            background: dragOver ? 'rgba(233,69,96,0.08)' : 'transparent',
            transition: 'all 0.2s',
            marginBottom: 16,
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.txt,.zip"
            style={{ display: 'none' }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
          />
          {file ? (
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#e94560' }}>{file.name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                {(file.size / 1024).toFixed(1)} KB - 点击重新选择
              </div>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: 28, marginBottom: 8 }}>+</div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                拖拽文件到此处，或点击选择
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, opacity: 0.7 }}>
                支持 .md / .zip
              </div>
            </div>
          )}
        </div>

        {/* Format info */}
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.6 }}>
          支持格式：<br />
          - 单个 SKILL.md（含 # Ability / # Persona / # Soul）<br />
          - zip 包（ability.md + persona.md + soul.md + 可选 meta.json）<br />
          - colleague-skill zip（work.md + persona.md）
        </div>

        {/* Name field */}
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>居民名称</label>
          <input
            type="text"
            value={name}
            onChange={(e) => { setName(e.target.value); setSlug(generateSlug(e.target.value)) }}
            placeholder="例如: Python Expert"
            style={{
              width: '100%', padding: '8px 12px', background: '#09090b', border: '1px solid #27272a',
              borderRadius: 6, color: 'white', fontSize: 13, outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Slug field */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Slug（唯一标识）</label>
          <input
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="例如: python-expert"
            style={{
              width: '100%', padding: '8px 12px', background: '#09090b', border: '1px solid #27272a',
              borderRadius: 6, color: 'white', fontSize: 13, outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Error */}
        {error && (
          <div style={{ background: 'rgba(233,69,96,0.12)', border: '1px solid rgba(233,69,96,0.3)', borderRadius: 6, padding: '8px 12px', marginBottom: 16, fontSize: 13, color: '#e94560' }}>
            {error}
          </div>
        )}

        {/* Success */}
        {success && (
          <div style={{ background: 'rgba(34,197,94,0.12)', border: '1px solid rgba(34,197,94,0.3)', borderRadius: 6, padding: '8px 12px', marginBottom: 16, fontSize: 13, color: '#22c55e' }}>
            导入成功！
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={handleClose}
            style={{ background: '#27272a', color: 'white', border: 'none', padding: '8px 18px', borderRadius: 'var(--radius)', fontSize: 13, cursor: 'pointer' }}
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={!file || !name.trim() || !slug.trim() || uploading || success}
            style={{
              background: (!file || !name.trim() || !slug.trim() || uploading || success) ? '#3f3f46' : '#e94560',
              color: 'white', border: 'none', padding: '8px 18px', borderRadius: 'var(--radius)',
              fontSize: 13, fontWeight: 600, cursor: uploading ? 'wait' : 'pointer',
              opacity: (!file || !name.trim() || !slug.trim() || uploading || success) ? 0.6 : 1,
            }}
          >
            {uploading ? '导入中...' : '导入'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function ResidentList({ onResidentCountChange, onEditResident }: { onResidentCountChange: (n: number) => void; onEditResident: (slug: string) => void }) {
  const [residents, setResidents] = useState<ResidentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [importOpen, setImportOpen] = useState(false)
  const token = useGameStore((s) => s.token)
  const navigate = useNavigate()

  const fetchResidents = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch(`${API}/profile/residents`, { headers: { Authorization: `Bearer ${token ?? ''}` } })
      if (resp.ok) { const data = await resp.json(); setResidents(data); onResidentCountChange(data.length) }
    } catch { /* ignore */ } finally { setLoading(false) }
  }, [token, onResidentCountChange])

  useEffect(() => { void fetchResidents() }, [fetchResidents])

  if (loading) return <div style={{ color: 'var(--text-muted)', padding: 20, textAlign: 'center' }}>加载中...</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700 }}>我的居民</h2>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={() => setImportOpen(true)}
            style={{ background: '#27272a', color: 'white', border: '1px solid #3f3f46', padding: '8px 18px', borderRadius: 'var(--radius)', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
          >
            导入 Skill
          </button>
          <button onClick={() => navigate('/forge')} style={{ background: 'var(--accent-red)', color: 'white', border: 'none', padding: '8px 18px', borderRadius: 'var(--radius)', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>+ 创建新居民</button>
        </div>
      </div>
      {residents.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🏘️</div>
          <div>还没有创建任何居民</div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 16 }}>
            <button onClick={() => setImportOpen(true)} style={{ background: '#27272a', color: 'white', border: '1px solid #3f3f46', padding: '10px 24px', borderRadius: 'var(--radius)', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>导入 Skill</button>
            <button onClick={() => navigate('/forge')} style={{ background: 'var(--accent-red)', color: 'white', border: 'none', padding: '10px 24px', borderRadius: 'var(--radius)', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>创建第一位居民</button>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {residents.map((r) => <ResidentCard key={r.id} resident={r} onEdit={onEditResident} />)}
        </div>
      )}
      <ImportModal open={importOpen} onClose={() => setImportOpen(false)} onSuccess={() => void fetchResidents()} />
    </div>
  )
}
