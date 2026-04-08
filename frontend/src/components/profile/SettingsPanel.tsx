import { useEffect, useState } from 'react'
import { useGameStore } from '../../stores/gameStore'
import {
  getSettings,
  updateAccount,
  updateCharacter,
  updateInteraction,
  updatePrivacy,
  updateLLM,
  testLLMConnection,
  updateEconomy,
  getSpriteTemplates,
  type AllSettings,
  type SpriteTemplate,
  type LLMSettings,
} from '../../services/api'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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

function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        width: '100%', padding: '8px 12px',
        background: 'var(--bg-input)', border: '1px solid var(--border)',
        borderRadius: 6, color: 'var(--text-primary)', fontSize: 13,
        outline: 'none', boxSizing: 'border-box',
      }}
    />
  )
}

function SaveButton({
  onClick,
  saving,
  saved,
}: {
  onClick: () => void
  saving: boolean
  saved: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={saving}
      style={{
        marginTop: 12, padding: '7px 20px',
        background: saved ? '#53d769' : 'var(--accent)',
        color: 'white', border: 'none', borderRadius: 6,
        fontSize: 13, fontWeight: 600, cursor: saving ? 'default' : 'pointer',
        transition: 'background 0.2s ease', opacity: saving ? 0.7 : 1,
      }}
    >
      {saving ? '保存中...' : saved ? '已保存 ✓' : '保存'}
    </button>
  )
}

function Toggle({
  value,
  onChange,
  label,
}: {
  value: boolean
  onChange: (v: boolean) => void
  label: string
}) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
      <div
        onClick={() => onChange(!value)}
        style={{
          width: 36, height: 20, borderRadius: 10,
          background: value ? 'var(--accent)' : 'var(--bg-input)',
          border: '1px solid var(--border)',
          position: 'relative', cursor: 'pointer', transition: 'background 0.2s',
          flexShrink: 0,
        }}
      >
        <div style={{
          position: 'absolute', top: 2,
          left: value ? 17 : 2,
          width: 14, height: 14, borderRadius: '50%',
          background: 'white', transition: 'left 0.2s',
        }} />
      </div>
      <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>{label}</span>
    </label>
  )
}

function Badge({
  label,
  active,
}: {
  label: string
  active: boolean
}) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: 20,
      fontSize: 12, fontWeight: 500,
      background: active ? '#53d76920' : 'var(--bg-input)',
      color: active ? '#53d769' : 'var(--text-muted)',
      border: `1px solid ${active ? '#53d769' : 'var(--border)'}`,
    }}>
      {active ? '✓' : '✗'} {label}
    </span>
  )
}

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '20px 24px', marginBottom: 16,
    }}>
      {children}
    </div>
  )
}

// ─── Account Section ─────────────────────────────────────────────

function AccountSection({ settings }: { settings: AllSettings }) {
  const setAuthUser = useGameStore((s) => s.setAuth)
  const token = useGameStore((s) => s.token)
  const user = useGameStore((s) => s.user)
  const [displayName, setDisplayName] = useState(settings.account.display_name)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const result = await updateAccount({ display_name: displayName })
      // Update store so TopNav/Sidebar reflects new name immediately
      if (user && token) {
        setAuthUser({ ...user, name: result.display_name }, token)
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  return (
    <SectionCard>
      <SectionHeader icon="👤" title="账号" />

      <div style={{ marginBottom: 16 }}>
        <FieldLabel>显示名称</FieldLabel>
        <div style={{ display: 'flex', gap: 8 }}>
          <TextInput value={displayName} onChange={setDisplayName} placeholder="输入显示名称" />
          <SaveButton onClick={() => void handleSave()} saving={saving} saved={saved} />
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <FieldLabel>邮箱</FieldLabel>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', padding: '8px 12px', background: 'var(--bg-input)', borderRadius: 6, border: '1px solid var(--border)' }}>
          {settings.account.email}
        </div>
      </div>

      <div>
        <FieldLabel>登录方式</FieldLabel>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Badge label="邮箱" active={settings.account.has_password} />
          <Badge label="GitHub" active={settings.account.github_bound} />
          <Badge label="LinuxDo" active={settings.account.linuxdo_bound} />
        </div>
      </div>
    </SectionCard>
  )
}

// ─── Character Section ───────────────────────────────────────────

function CharacterSection({ settings }: { settings: AllSettings }) {
  const character = settings.character
  const [sprites, setSprites] = useState<SpriteTemplate[]>([])
  const [selectedSprite, setSelectedSprite] = useState(character?.sprite_key ?? '')
  const [characterName, setCharacterName] = useState(character?.name ?? '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loadingSprites, setLoadingSprites] = useState(true)

  useEffect(() => {
    const loadSprites = async () => {
      try {
        const templates = await getSpriteTemplates()
        setSprites(templates)
      } catch { /* ignore */ }
      finally { setLoadingSprites(false) }
    }
    void loadSprites()
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await updateCharacter({ name: characterName, sprite_key: selectedSprite })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  if (!character) {
    return (
      <SectionCard>
        <SectionHeader icon="🧑‍🎤" title="角色" />
        <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
          暂无绑定角色。前往地图创建你的居民后再来设置。
        </div>
      </SectionCard>
    )
  }

  return (
    <SectionCard>
      <SectionHeader icon="🧑‍🎤" title="角色" />

      <div style={{ display: 'flex', gap: 24, marginBottom: 20 }}>
        {/* Current sprite preview */}
        <div style={{ flexShrink: 0 }}>
          <FieldLabel>当前形象</FieldLabel>
          <div style={{
            width: 72, height: 72,
            background: 'var(--bg-input)', border: '1px solid var(--border)',
            borderRadius: 10, overflow: 'hidden',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <img
              src={`${API}/assets/village/agents/${selectedSprite}/texture.png`}
              alt={selectedSprite}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              onError={(e) => {
                const target = e.target as HTMLImageElement
                target.style.display = 'none'
                if (target.parentElement) {
                  target.parentElement.style.fontSize = '32px'
                  target.parentElement.textContent = '🧑'
                }
              }}
            />
          </div>
        </div>

        {/* Character name */}
        <div style={{ flex: 1 }}>
          <FieldLabel>角色名称</FieldLabel>
          <TextInput value={characterName} onChange={setCharacterName} placeholder="输入角色名称" />
        </div>
      </div>

      {/* Sprite selection grid */}
      <div>
        <FieldLabel>选择形象（点击切换）</FieldLabel>
        {loadingSprites ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>加载形象列表...</div>
        ) : (
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(56px, 1fr))',
            gap: 8,
          }}>
            {sprites.map((sprite) => (
              <div
                key={sprite.key}
                title={`${sprite.key} · ${sprite.vibe}`}
                onClick={() => setSelectedSprite(sprite.key)}
                style={{
                  width: 56, height: 56,
                  background: selectedSprite === sprite.key ? 'var(--accent)10' : 'var(--bg-input)',
                  border: selectedSprite === sprite.key
                    ? '2px solid var(--accent)'
                    : '1px solid var(--border)',
                  borderRadius: 8, overflow: 'hidden', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'border-color 0.15s',
                }}
              >
                <img
                  src={`${API}/assets/village/agents/${sprite.key}/texture.png`}
                  alt={sprite.key}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  onError={(e) => {
                    const target = e.target as HTMLImageElement
                    target.style.display = 'none'
                    if (target.parentElement) {
                      target.parentElement.style.fontSize = '20px'
                      target.parentElement.textContent = '🧑'
                    }
                  }}
                />
              </div>
            ))}
          </div>
        )}
        {selectedSprite && (
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
            已选：{selectedSprite}
          </div>
        )}
      </div>

      <SaveButton onClick={() => void handleSave()} saving={saving} saved={saved} />
    </SectionCard>
  )
}

// ─── Interaction Section ─────────────────────────────────────────

function InteractionSection({ settings }: { settings: AllSettings }) {
  const interaction = settings.interaction as {
    reply_mode?: string
    offline_auto_reply?: boolean
    notification_chat?: boolean
    notification_system?: boolean
  }

  const [replyMode, setReplyMode] = useState<'manual' | 'auto'>(
    (interaction.reply_mode as 'manual' | 'auto') ?? 'manual'
  )
  const [offlineAutoReply, setOfflineAutoReply] = useState(interaction.offline_auto_reply ?? false)
  const [notificationChat, setNotificationChat] = useState(interaction.notification_chat ?? true)
  const [notificationSystem, setNotificationSystem] = useState(interaction.notification_system ?? true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await updateInteraction({
        reply_mode: replyMode,
        offline_auto_reply: offlineAutoReply,
        notification_chat: notificationChat,
        notification_system: notificationSystem,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  return (
    <SectionCard>
      <SectionHeader icon="💬" title="互动设置" />

      <div style={{ marginBottom: 16 }}>
        <FieldLabel>回复模式</FieldLabel>
        <div style={{ display: 'flex', gap: 8 }}>
          {(['manual', 'auto'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setReplyMode(mode)}
              style={{
                padding: '7px 18px', borderRadius: 6, fontSize: 13,
                fontWeight: replyMode === mode ? 600 : 400,
                cursor: 'pointer',
                background: replyMode === mode ? 'var(--accent)' : 'var(--bg-input)',
                color: replyMode === mode ? 'white' : 'var(--text-secondary)',
                border: replyMode === mode ? '1px solid var(--accent)' : '1px solid var(--border)',
                transition: 'background 0.15s',
              }}
            >
              {mode === 'manual' ? '手动' : '自动'}
            </button>
          ))}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
          {replyMode === 'manual' ? '访客发起对话后，由你手动决定是否用 AI 回复' : '访客消息自动由 AI 角色回复'}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
        <Toggle value={offlineAutoReply} onChange={setOfflineAutoReply} label="离线时自动回复" />
        <Toggle value={notificationChat} onChange={setNotificationChat} label="新对话通知" />
        <Toggle value={notificationSystem} onChange={setNotificationSystem} label="系统通知" />
      </div>

      <SaveButton onClick={() => void handleSave()} saving={saving} saved={saved} />
    </SectionCard>
  )
}

// ─── Privacy Section ─────────────────────────────────────────────

type PersonaVisibility = 'full' | 'identity_card_only' | 'hidden'

function PrivacySection({ settings }: { settings: AllSettings }) {
  const privacy = settings.privacy as {
    map_visible?: boolean
    persona_visibility?: PersonaVisibility
    allow_conversation_stats?: boolean
  }

  const [mapVisible, setMapVisible] = useState(privacy.map_visible ?? true)
  const [personaVisibility, setPersonaVisibility] = useState<PersonaVisibility>(
    privacy.persona_visibility ?? 'full'
  )
  const [allowStats, setAllowStats] = useState(privacy.allow_conversation_stats ?? true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await updatePrivacy({
        map_visible: mapVisible,
        persona_visibility: personaVisibility,
        allow_conversation_stats: allowStats,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  const visibilityOptions: { value: PersonaVisibility; label: string; desc: string }[] = [
    { value: 'full', label: '完整公开', desc: '所有人可查看角色的完整设定' },
    { value: 'identity_card_only', label: '仅身份卡', desc: '只显示名称和基本信息' },
    { value: 'hidden', label: '隐藏', desc: '对他人完全隐藏角色信息' },
  ]

  return (
    <SectionCard>
      <SectionHeader icon="🔒" title="隐私设置" />

      <div style={{ marginBottom: 16 }}>
        <Toggle value={mapVisible} onChange={setMapVisible} label="在地图上显示我的角色" />
      </div>

      <div style={{ marginBottom: 16 }}>
        <FieldLabel>角色信息可见范围</FieldLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {visibilityOptions.map((opt) => (
            <label
              key={opt.value}
              onClick={() => setPersonaVisibility(opt.value)}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 10,
                padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
                background: personaVisibility === opt.value ? 'var(--accent)10' : 'var(--bg-input)',
                border: personaVisibility === opt.value
                  ? '1px solid var(--accent)'
                  : '1px solid var(--border)',
                transition: 'border-color 0.15s',
              }}
            >
              <div style={{
                width: 16, height: 16, borderRadius: '50%', flexShrink: 0, marginTop: 1,
                border: `2px solid ${personaVisibility === opt.value ? 'var(--accent)' : 'var(--border)'}`,
                background: personaVisibility === opt.value ? 'var(--accent)' : 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {personaVisibility === opt.value && (
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'white' }} />
                )}
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{opt.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{opt.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Toggle value={allowStats} onChange={setAllowStats} label="允许统计对话数据（用于排行榜）" />
      </div>

      <SaveButton onClick={() => void handleSave()} saving={saving} saved={saved} />
    </SectionCard>
  )
}

// ─── LLM Section ─────────────────────────────────────────────────

function LLMSection({ settings }: { settings: AllSettings }) {
  const llm = settings.llm as LLMSettings

  const systemAllows = llm.system_allows_custom !== false
  const [enabled, setEnabled] = useState(llm.custom_llm_enabled ?? false)
  const [apiFormat, setApiFormat] = useState<'openai' | 'anthropic'>(llm.api_format ?? 'openai')
  const [baseUrl, setBaseUrl] = useState(llm.base_url ?? '')
  const [apiKey, setApiKey] = useState(llm.api_key ?? '')
  const [model, setModel] = useState(llm.model ?? '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await updateLLM({
        custom_llm_enabled: enabled,
        api_format: apiFormat,
        base_url: baseUrl,
        api_key: apiKey,
        model,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testLLMConnection({ api_format: apiFormat, base_url: baseUrl, api_key: apiKey, model })
      setTestResult(result)
    } catch (err: unknown) {
      setTestResult({ success: false, message: err instanceof Error ? err.message : '连接失败' })
    } finally {
      setTesting(false)
    }
  }

  return (
    <SectionCard>
      <SectionHeader icon="🤖" title="LLM 设置" />

      {!systemAllows && (
        <div style={{
          padding: '10px 12px', borderRadius: 8, marginBottom: 16,
          background: 'var(--bg-input)', border: '1px solid var(--border)',
          fontSize: 13, color: 'var(--text-muted)',
        }}>
          系统当前未开放自定义 LLM 接入。
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <Toggle
          value={enabled}
          onChange={setEnabled}
          label="启用自定义 LLM"
        />
      </div>

      {enabled && (
        <>
          <div style={{ marginBottom: 16 }}>
            <FieldLabel>API 格式</FieldLabel>
            <div style={{ display: 'flex', gap: 8 }}>
              {(['openai', 'anthropic'] as const).map((fmt) => (
                <button
                  key={fmt}
                  onClick={() => setApiFormat(fmt)}
                  style={{
                    padding: '7px 18px', borderRadius: 6, fontSize: 13,
                    fontWeight: apiFormat === fmt ? 600 : 400,
                    cursor: 'pointer',
                    background: apiFormat === fmt ? 'var(--accent)' : 'var(--bg-input)',
                    color: apiFormat === fmt ? 'white' : 'var(--text-secondary)',
                    border: apiFormat === fmt ? '1px solid var(--accent)' : '1px solid var(--border)',
                    transition: 'background 0.15s',
                  }}
                >
                  {fmt === 'openai' ? 'OpenAI 兼容' : 'Anthropic 兼容'}
                </button>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: 12 }}>
            <FieldLabel>Base URL</FieldLabel>
            <TextInput
              value={baseUrl}
              onChange={setBaseUrl}
              placeholder="https://api.openai.com/v1"
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <FieldLabel>API Key</FieldLabel>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              style={{
                width: '100%', padding: '8px 12px',
                background: 'var(--bg-input)', border: '1px solid var(--border)',
                borderRadius: 6, color: 'var(--text-primary)', fontSize: 13,
                outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <FieldLabel>模型名称</FieldLabel>
            <TextInput
              value={model}
              onChange={setModel}
              placeholder="gpt-4o / claude-3-5-sonnet-20241022"
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <button
              onClick={() => void handleTest()}
              disabled={testing || !baseUrl || !apiKey || !model}
              style={{
                padding: '7px 20px',
                background: 'var(--bg-input)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                borderRadius: 6, fontSize: 13, fontWeight: 600,
                cursor: testing || !baseUrl || !apiKey || !model ? 'default' : 'pointer',
                opacity: testing || !baseUrl || !apiKey || !model ? 0.6 : 1,
                transition: 'opacity 0.15s',
              }}
            >
              {testing ? '测试中...' : '测试连接'}
            </button>

            {testResult !== null && (
              <span style={{
                fontSize: 13,
                color: testResult.success ? '#53d769' : '#ff6b6b',
                fontWeight: 500,
              }}>
                {testResult.success ? '✓ ' : '✗ '}{testResult.message}
              </span>
            )}
          </div>
        </>
      )}

      <SaveButton onClick={() => void handleSave()} saving={saving} saved={saved} />
    </SectionCard>
  )
}

// ─── Economy Section ──────────────────────────────────────────────

function EconomySection({ settings }: { settings: AllSettings }) {
  const economy = settings.economy as {
    balance?: number
    low_balance_alert?: number
  }

  const [alertThreshold, setAlertThreshold] = useState(
    String(economy.low_balance_alert ?? '')
  )
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const parsed = parseFloat(alertThreshold)
      await updateEconomy({ low_balance_alert: isNaN(parsed) ? undefined : parsed })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  const balance = economy.balance

  return (
    <SectionCard>
      <SectionHeader icon="💰" title="灵魂币 & 经济" />

      <div style={{ marginBottom: 20 }}>
        <FieldLabel>当前余额</FieldLabel>
        <div style={{
          display: 'inline-flex', alignItems: 'baseline', gap: 6,
          padding: '10px 16px',
          background: 'var(--bg-input)', border: '1px solid var(--border)',
          borderRadius: 8,
        }}>
          <span style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>
            {balance !== undefined ? balance.toLocaleString() : '—'}
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>灵魂币</span>
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <FieldLabel>低余额提醒阈值</FieldLabel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="number"
            value={alertThreshold}
            onChange={(e) => setAlertThreshold(e.target.value)}
            placeholder="例如 100"
            min={0}
            style={{
              width: 140, padding: '8px 12px',
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              borderRadius: 6, color: 'var(--text-primary)', fontSize: 13,
              outline: 'none', boxSizing: 'border-box',
            }}
          />
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>灵魂币</span>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
          余额低于此值时，系统将发送通知提醒你充值
        </div>
      </div>

      <SaveButton onClick={() => void handleSave()} saving={saving} saved={saved} />
    </SectionCard>
  )
}

// ─── Main SettingsPanel ──────────────────────────────────────────

export function SettingsPanel() {
  const [settings, setSettings] = useState<AllSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await getSettings()
        setSettings(data)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '加载失败')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  if (loading) {
    return (
      <div style={{ color: 'var(--text-muted)', padding: 40, textAlign: 'center' }}>
        加载设置...
      </div>
    )
  }

  if (error || !settings) {
    return (
      <div style={{ color: '#ff6b6b', padding: 40, textAlign: 'center' }}>
        {error ?? '加载失败，请刷新重试'}
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 680 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 24, color: 'var(--text-primary)' }}>
        设置
      </h1>
      <AccountSection settings={settings} />
      <CharacterSection settings={settings} />
      <InteractionSection settings={settings} />
      <PrivacySection settings={settings} />
      <LLMSection settings={settings} />
      <EconomySection settings={settings} />
    </div>
  )
}
