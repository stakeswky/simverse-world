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
          <div style={{ fontWeight: 800, fontSize: 18, marginTop: 4 }}>Skills World</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            一座永不关闭的赛博城市
          </div>
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
