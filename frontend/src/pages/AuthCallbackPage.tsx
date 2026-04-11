import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGameStore } from '../stores/gameStore'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function AuthCallbackPage() {
  const [error, setError] = useState('')
  const setAuth = useGameStore((s) => s.setAuth)
  const navigate = useNavigate()

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const token = params.get('token')

    if (!token) {
      setError('登录失败：未收到 token')
      const timer = setTimeout(() => navigate('/login', { replace: true }), 2000)
      return () => clearTimeout(timer)
    }

    const fetchUser = async () => {
      try {
        const resp = await fetch(`${API}/users/me`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!resp.ok) {
          setError('登录失败：无法获取用户信息')
          const timer = setTimeout(() => navigate('/login', { replace: true }), 2000)
          return () => clearTimeout(timer)
        }
        const user = await resp.json()
        setAuth(user, token)
        navigate('/onboarding', { replace: true })
      } catch {
        setError('网络错误，请重试')
        const timer = setTimeout(() => navigate('/login', { replace: true }), 2000)
        return () => clearTimeout(timer)
      }
    }

    fetchUser()
  }, [navigate, setAuth])

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%)',
    }}>
      <div style={{
        background: '#18181bf0', border: '1px solid var(--border)', borderRadius: 16,
        padding: 32, width: 340, backdropFilter: 'blur(12px)', textAlign: 'center',
      }}>
        {error ? (
          <>
            <div style={{ fontSize: 28, marginBottom: 12 }}>⚠️</div>
            <div style={{ color: 'var(--accent-red)', fontSize: 14, marginBottom: 8 }}>{error}</div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>正在跳转到登录页...</div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 28, marginBottom: 12 }}>🏙️</div>
            <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 8 }}>正在登录中...</div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>请稍候</div>
          </>
        )}
      </div>
    </div>
  )
}
