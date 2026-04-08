import { useEffect, useState } from 'react'
import { getAdminSystemConfig, updateAdminSystemConfig } from '../../services/api'

// ─── Shared sub-components ────────────────────────────────────────

function SectionHeader({ icon, title }: { icon: string; title: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      marginBottom: 20, paddingBottom: 12,
      borderBottom: '1px solid var(--border)',
    }}>
      <span style={{ fontSize: 18 }}>{icon}</span>
      <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>{title}</h2>
    </div>
  )
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 500 }}>
      {children}
    </div>
  )
}

function SaveButton({ onClick, saving, saved, disabled }: {
  onClick: () => void
  saving: boolean
  saved: boolean
  disabled?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={saving || disabled}
      style={{
        marginTop: 16, padding: '7px 20px',
        background: saved ? '#53d769' : 'var(--accent)',
        color: 'white', border: 'none', borderRadius: 6,
        fontSize: 13, fontWeight: 600,
        cursor: saving || disabled ? 'default' : 'pointer',
        transition: 'background 0.2s ease',
        opacity: saving || disabled ? 0.7 : 1,
      }}
    >
      {saving ? '保存中...' : saved ? '已保存 ✓' : '保存'}
    </button>
  )
}

// ─── Config field types ───────────────────────────────────────────

type FieldType = 'text' | 'number' | 'float'

interface FieldDef {
  key: string
  label: string
  type: FieldType
  hint?: string
}

// ─── Generic Config Section ───────────────────────────────────────

interface ConfigSectionProps {
  token: string
  icon: string
  title: string
  group: string
  fields: FieldDef[]
  defaultOpen?: boolean
}

function ConfigSection({ token, icon, title, group, fields, defaultOpen = false }: ConfigSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  const [values, setValues] = useState<Record<string, string>>({})
  const [loaded, setLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || loaded) return
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await getAdminSystemConfig(token, group)
        const initial: Record<string, string> = {}
        for (const field of fields) {
          const raw = data[field.key]
          initial[field.key] = raw !== undefined && raw !== null ? String(raw) : ''
        }
        setValues(initial)
        setLoaded(true)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [open, loaded, token, group, fields])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      for (const field of fields) {
        const raw = values[field.key]
        let parsed: unknown = raw
        if (field.type === 'number') {
          parsed = parseInt(raw, 10)
        } else if (field.type === 'float') {
          parsed = parseFloat(raw)
        }
        await updateAdminSystemConfig(token, field.key, parsed, group)
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const setField = (key: string, value: string) => {
    setValues((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 10, marginBottom: 12, overflow: 'hidden',
    }}>
      {/* Accordion header */}
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center',
          gap: 10, padding: '14px 20px',
          background: 'transparent', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{ fontSize: 18 }}>{icon}</span>
        <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        <span style={{
          fontSize: 12, color: 'var(--text-muted)',
          transform: open ? 'rotate(180deg)' : 'none',
          transition: 'transform 0.2s',
          display: 'inline-block',
        }}>▼</span>
      </button>

      {/* Accordion body */}
      {open && (
        <div style={{ padding: '4px 20px 20px 20px', borderTop: '1px solid var(--border)' }}>
          {loading ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '12px 0' }}>加载配置...</div>
          ) : error && !loaded ? (
            <div style={{ color: '#ff6b6b', fontSize: 13, padding: '12px 0' }}>{error}</div>
          ) : (
            <>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                gap: '0 24px',
                marginTop: 16,
              }}>
                {fields.map((field) => (
                  <div key={field.key} style={{ marginBottom: 14 }}>
                    <FieldLabel>{field.label}</FieldLabel>
                    <input
                      type={field.type === 'text' ? 'text' : 'number'}
                      value={values[field.key] ?? ''}
                      onChange={(e) => setField(field.key, e.target.value)}
                      step={field.type === 'float' ? 'any' : '1'}
                      style={{
                        width: '100%', padding: '8px 12px',
                        background: 'var(--bg-input)', border: '1px solid var(--border)',
                        borderRadius: 6, color: 'var(--text-primary)', fontSize: 13,
                        outline: 'none', boxSizing: 'border-box',
                      }}
                    />
                    {field.hint && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{field.hint}</div>
                    )}
                  </div>
                ))}
              </div>

              {error && (
                <div style={{ color: '#ff6b6b', fontSize: 13, marginTop: 4 }}>{error}</div>
              )}

              <SaveButton onClick={() => void handleSave()} saving={saving} saved={saved} disabled={!loaded} />
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Group definitions ────────────────────────────────────────────

const LLM_FIELDS: FieldDef[] = [
  { key: 'model', label: '模型名称 (model)', type: 'text', hint: '例：gpt-4o / claude-3-5-sonnet-20241022' },
  { key: 'base_url', label: '接口地址 (base_url)', type: 'text', hint: 'LLM API 的 base URL' },
  { key: 'temperature', label: '温度 (temperature)', type: 'float', hint: '生成多样性，0.0 – 2.0' },
  { key: 'timeout', label: '超时时间 (timeout)', type: 'number', hint: '单次请求超时，单位秒' },
  { key: 'max_retries', label: '最大重试 (max_retries)', type: 'number', hint: '失败后最多重试次数' },
  { key: 'concurrency', label: '并发数 (concurrency)', type: 'number', hint: '最大并行请求数' },
]

const HEAT_FIELDS: FieldDef[] = [
  { key: 'popular_threshold', label: '热门阈值 (popular_threshold)', type: 'number', hint: '热度值超过此数视为热门' },
  { key: 'sleeping_days', label: '休眠天数 (sleeping_days)', type: 'number', hint: '超过此天数无对话则进入休眠' },
  { key: 'cron_interval', label: '计算间隔 (cron_interval)', type: 'number', hint: '热度计算定时任务间隔，单位分钟' },
]

const RATING_FIELDS: FieldDef[] = [
  { key: 'min_content_length', label: '最小内容长度 (min_content_length)', type: 'number', hint: '角色文本最短字数（低于此不评分）' },
  { key: 'star3_min_conversations', label: '三星最少对话数 (star3_min_conversations)', type: 'number', hint: '达到 3 星所需最少完整对话轮数' },
  { key: 'star3_min_rating', label: '三星最低评分 (star3_min_rating)', type: 'float', hint: '达到 3 星所需最低平均评分' },
]

// ─── Main SystemConfigPanel ───────────────────────────────────────

interface SystemConfigPanelProps {
  token: string
}

export function SystemConfigPanel({ token }: SystemConfigPanelProps) {
  return (
    <div style={{ maxWidth: 900 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>
        系统配置
      </h1>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 24 }}>
        点击各分组展开配置项，修改后点击「保存」生效。
      </p>

      <ConfigSection
        token={token}
        icon="🤖"
        title="LLM 配置"
        group="llm"
        fields={LLM_FIELDS}
        defaultOpen
      />
      <ConfigSection
        token={token}
        icon="🔥"
        title="热度规则"
        group="heat"
        fields={HEAT_FIELDS}
      />
      <ConfigSection
        token={token}
        icon="⭐"
        title="评分规则"
        group="rating"
        fields={RATING_FIELDS}
      />
    </div>
  )
}
