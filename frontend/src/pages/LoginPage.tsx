import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGameStore } from '../stores/gameStore'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [isRegister, setIsRegister] = useState(false)
  const [error, setError] = useState('')
  const setAuth = useGameStore((s) => s.setAuth)
  const navigate = useNavigate()

  const submit = async () => {
    setError('')
    const endpoint = isRegister ? '/auth/register' : '/auth/login'
    const body = isRegister ? { name, email, password } : { email, password }
    try {
      const resp = await fetch(`${API}${endpoint}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        setError(err.detail || '操作失败')
        return
      }
      const data = await resp.json()
      setAuth(data.user, data.access_token)
      navigate('/onboarding')
    } catch {
      setError('网络错误，请重试')
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', background: 'var(--bg-input)', border: '1px solid var(--border)',
    color: 'var(--text-primary)', padding: '10px 14px', borderRadius: 'var(--radius)',
    fontSize: 14, outline: 'none', marginBottom: 8,
  }

  const oauthBtnStyle: React.CSSProperties = {
    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    padding: 10, borderRadius: 'var(--radius)', fontSize: 13, fontWeight: 600,
    cursor: 'pointer', border: '1px solid var(--border)', background: 'var(--bg-input)',
    color: 'var(--text-primary)', transition: 'background 0.15s',
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%)',
    }}>
      <div style={{
        background: '#18181bf0', border: '1px solid var(--border)', borderRadius: 16,
        padding: 32, width: 340, backdropFilter: 'blur(12px)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div style={{ fontSize: 28 }}>🏙️</div>
          <div style={{ fontWeight: 800, fontSize: 18, marginTop: 4 }}>Simverse World</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            一座永不关闭的赛博城市
          </div>
        </div>

        {/* OAuth Buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          <a href={`${API}/auth/github/login`} style={{ textDecoration: 'none' }}>
            <div style={oauthBtnStyle}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#27272a' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--bg-input)' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
              </svg>
              GitHub 登录
            </div>
          </a>
          <a href={`${API}/auth/linuxdo/login`} style={{ textDecoration: 'none' }}>
            <div style={oauthBtnStyle}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#27272a' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--bg-input)' }}>
              <span style={{ fontSize: 16 }}>🐧</span>
              LinuxDo 登录
            </div>
          </a>
        </div>

        {/* Divider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>或使用邮箱</span>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
        </div>

        {isRegister && (
          <input style={inputStyle} placeholder="名字" value={name} onChange={(e) => setName(e.target.value)} />
        )}
        <input style={inputStyle} placeholder="邮箱" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input style={{ ...inputStyle, marginBottom: error ? 4 : 8 }} placeholder="密码" type="password"
          value={password} onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()} />
        {error && <div style={{ color: 'var(--accent-red)', fontSize: 12, marginBottom: 8 }}>{error}</div>}
        <button onClick={submit} style={{
          width: '100%', background: 'var(--accent-red)', color: 'white', border: 'none',
          padding: 10, borderRadius: 'var(--radius)', fontSize: 14, fontWeight: 700, cursor: 'pointer',
        }}>{isRegister ? '注册并进入城市' : '进入城市'}</button>
        <div style={{ textAlign: 'center', marginTop: 10, color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer' }}
          onClick={() => setIsRegister(!isRegister)}>
          {isRegister ? '已有账号？登录' : '没有账号？注册'}
        </div>
      </div>
    </div>
  )
}
