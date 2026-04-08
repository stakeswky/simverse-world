import { useEffect, useState, useCallback, useRef } from 'react'
import { useGameStore } from '../../stores/gameStore'
import {
  getAdminUsers,
  adminAdjustCoin,
  adminPatchUser,
  type AdminUserListItem,
} from '../../services/api'

// ─── Types ────────────────────────────────────────────────────────

interface AdjustCoinModalProps {
  user: AdminUserListItem
  onClose: () => void
  onSuccess: (updatedBalance: number) => void
}

// ─── Helpers ──────────────────────────────────────────────────────

function loginMethodIcon(method: string): string {
  if (method === 'github') return '🐙'
  if (method === 'linuxdo') return '🐧'
  if (method === 'password') return '🔑'
  return '🔗'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

// ─── Balance Adjust Modal ─────────────────────────────────────────

function AdjustCoinModal({ user, onClose, onSuccess }: AdjustCoinModalProps) {
  const token = useGameStore((s) => s.token)
  const [amount, setAmount] = useState<string>('')
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSubmit = async () => {
    const parsed = parseInt(amount, 10)
    if (isNaN(parsed) || parsed === 0) {
      setError('请输入有效的金额（非零整数）')
      return
    }
    if (!reason.trim()) {
      setError('请填写调整原因')
      return
    }
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const result = await adminAdjustCoin(token, user.id, { amount: parsed, reason: reason.trim() })
      onSuccess(result.new_balance)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
  }

  return (
    <div
      onKeyDown={handleKeyDown}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: 28,
        width: 380,
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>调整 Soul Coin 余额</h3>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        <div style={{ fontSize: 13, color: 'var(--text-secondary)', background: 'var(--bg-input)', borderRadius: 8, padding: '10px 14px' }}>
          <div>{user.name} <span style={{ color: 'var(--text-muted)' }}>({user.email})</span></div>
          <div style={{ marginTop: 4, color: 'var(--accent-green)' }}>当前余额：🪙 {user.soul_coin_balance}</div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>调整金额（正数增加，负数扣减）</label>
          <input
            ref={inputRef}
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="例如：100 或 -50"
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '8px 12px',
              color: 'var(--text-primary)',
              fontSize: 14,
              outline: 'none',
            }}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>调整原因</label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="例如：活动奖励、补偿"
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '8px 12px',
              color: 'var(--text-primary)',
              fontSize: 14,
              outline: 'none',
            }}
          />
        </div>

        {error && (
          <div style={{ fontSize: 13, color: '#ef4444', background: '#ef444415', padding: '8px 12px', borderRadius: 6 }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '8px 18px',
              fontSize: 13,
              cursor: 'pointer',
              color: 'var(--text-secondary)',
            }}
          >
            取消
          </button>
          <button
            onClick={() => { void handleSubmit() }}
            disabled={loading}
            style={{
              background: loading ? 'var(--bg-input)' : 'var(--accent-blue)',
              border: 'none',
              borderRadius: 6,
              padding: '8px 18px',
              fontSize: 13,
              cursor: loading ? 'default' : 'pointer',
              color: loading ? 'var(--text-muted)' : 'white',
              fontWeight: 600,
            }}
          >
            {loading ? '处理中…' : '确认调整'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Table Row ────────────────────────────────────────────────────

interface UserRowProps {
  user: AdminUserListItem
  onAdjustCoin: (user: AdminUserListItem) => void
  onToggleBan: (user: AdminUserListItem) => void
  onToggleAdmin: (user: AdminUserListItem) => void
  actionLoading: string | null
}

function UserRow({ user, onAdjustCoin, onToggleBan, onToggleAdmin, actionLoading }: UserRowProps) {
  const isLoading = actionLoading === user.id
  const cellStyle: React.CSSProperties = {
    padding: '12px 14px',
    fontSize: 13,
    borderBottom: '1px solid var(--border)',
    color: 'var(--text-secondary)',
    verticalAlign: 'middle',
  }

  return (
    <tr style={{ transition: 'background 0.12s' }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'rgba(255,255,255,0.035)' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = '' }}
    >
      <td style={{ ...cellStyle, color: 'var(--text-primary)', fontWeight: 500 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28, height: 28, borderRadius: '50%',
            background: 'var(--bg-input)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', flexShrink: 0,
          }}>
            {user.name?.[0]?.toUpperCase() ?? '?'}
          </div>
          <span style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {user.name}
          </span>
          {user.is_admin && (
            <span style={{ fontSize: 10, background: '#a78bfa22', color: '#a78bfa', padding: '1px 6px', borderRadius: 4, fontWeight: 600, flexShrink: 0 }}>管理员</span>
          )}
        </div>
      </td>
      <td style={{ ...cellStyle, maxWidth: 180 }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
          {user.email}
        </span>
      </td>
      <td style={{ ...cellStyle, textAlign: 'center' }}>
        <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
          {(user.login_methods ?? []).map((m) => (
            <span key={m} title={m} style={{ fontSize: 16 }}>{loginMethodIcon(m)}</span>
          ))}
          {(!user.login_methods || user.login_methods.length === 0) && (
            <span style={{ color: 'var(--text-muted)' }}>—</span>
          )}
        </div>
      </td>
      <td style={{ ...cellStyle, textAlign: 'right', color: 'var(--accent-green)', fontWeight: 600 }}>
        🪙 {user.soul_coin_balance}
      </td>
      <td style={{ ...cellStyle, textAlign: 'center' }}>
        {user.resident_count}
      </td>
      <td style={cellStyle}>
        {formatDate(user.created_at)}
      </td>
      <td style={{ ...cellStyle, textAlign: 'center' }}>
        <span style={{
          fontSize: 11,
          fontWeight: 600,
          padding: '3px 8px',
          borderRadius: 4,
          background: user.is_banned ? '#ef444420' : '#22c55e20',
          color: user.is_banned ? '#ef4444' : '#22c55e',
        }}>
          {user.is_banned ? '已封禁' : '正常'}
        </span>
      </td>
      <td style={{ ...cellStyle }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'nowrap' }}>
          <button
            onClick={() => onAdjustCoin(user)}
            disabled={isLoading}
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              borderRadius: 5,
              padding: '4px 10px',
              fontSize: 11,
              cursor: isLoading ? 'default' : 'pointer',
              color: isLoading ? 'var(--text-muted)' : 'var(--accent-green)',
              whiteSpace: 'nowrap',
              fontWeight: 600,
            }}
          >
            调整余额
          </button>
          <button
            onClick={() => onToggleBan(user)}
            disabled={isLoading}
            style={{
              background: user.is_banned ? '#ef444418' : 'var(--bg-input)',
              border: `1px solid ${user.is_banned ? '#ef444440' : 'var(--border)'}`,
              borderRadius: 5,
              padding: '4px 10px',
              fontSize: 11,
              cursor: isLoading ? 'default' : 'pointer',
              color: isLoading ? 'var(--text-muted)' : (user.is_banned ? '#ef4444' : 'var(--text-secondary)'),
              whiteSpace: 'nowrap',
              fontWeight: 600,
            }}
          >
            {isLoading ? '…' : (user.is_banned ? '解封' : '封禁')}
          </button>
          <button
            onClick={() => onToggleAdmin(user)}
            disabled={isLoading}
            style={{
              background: user.is_admin ? '#a78bfa18' : 'var(--bg-input)',
              border: `1px solid ${user.is_admin ? '#a78bfa40' : 'var(--border)'}`,
              borderRadius: 5,
              padding: '4px 10px',
              fontSize: 11,
              cursor: isLoading ? 'default' : 'pointer',
              color: isLoading ? 'var(--text-muted)' : (user.is_admin ? '#a78bfa' : 'var(--text-secondary)'),
              whiteSpace: 'nowrap',
              fontWeight: 600,
            }}
          >
            {user.is_admin ? '取消管理员' : '设为管理员'}
          </button>
        </div>
      </td>
    </tr>
  )
}

// ─── Main Panel ───────────────────────────────────────────────────

export function UsersPanel() {
  const token = useGameStore((s) => s.token)
  const [users, setUsers] = useState<AdminUserListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [perPage] = useState(20)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [adjustTarget, setAdjustTarget] = useState<AdminUserListItem | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const totalPages = Math.max(1, Math.ceil(total / perPage))

  const fetchUsers = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const result = await getAdminUsers(token, { page, per_page: perPage, search: search || undefined })
      setUsers(result.items)
      setTotal(result.total)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [token, page, perPage, search])

  useEffect(() => {
    void fetchUsers()
  }, [fetchUsers])

  const handleSearch = () => {
    setSearch(searchInput)
    setPage(1)
  }

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSearch()
  }

  const handleAdjustCoinSuccess = (userId: string, newBalance: number) => {
    setUsers((prev) =>
      prev.map((u) => (u.id === userId ? { ...u, soul_coin_balance: newBalance } : u))
    )
    setAdjustTarget(null)
  }

  const handleToggleBan = async (user: AdminUserListItem) => {
    if (!token) return
    setActionLoading(user.id)
    try {
      const updated = await adminPatchUser(token, user.id, { is_banned: !user.is_banned })
      setUsers((prev) => prev.map((u) => (u.id === user.id ? { ...u, is_banned: updated.is_banned } : u)))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setActionLoading(null)
    }
  }

  const handleToggleAdmin = async (user: AdminUserListItem) => {
    if (!token) return
    setActionLoading(user.id)
    try {
      const updated = await adminPatchUser(token, user.id, { is_admin: !user.is_admin })
      setUsers((prev) => prev.map((u) => (u.id === user.id ? { ...u, is_admin: updated.is_admin } : u)))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setActionLoading(null)
    }
  }

  const btnBase: React.CSSProperties = {
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    padding: '6px 14px',
    fontSize: 12,
    cursor: 'pointer',
    color: 'var(--text-secondary)',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>👥 用户管理</h2>

        {/* Search bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <span style={{ position: 'absolute', left: 10, fontSize: 14, color: 'var(--text-muted)', pointerEvents: 'none' }}>🔍</span>
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="搜索用户名 / 邮箱…"
              style={{
                background: 'var(--bg-input)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '7px 12px 7px 34px',
                color: 'var(--text-primary)',
                fontSize: 13,
                outline: 'none',
                width: 240,
              }}
            />
          </div>
          <button
            onClick={handleSearch}
            style={{
              ...btnBase,
              background: 'var(--accent-blue)',
              color: 'white',
              border: 'none',
              fontWeight: 600,
            }}
          >
            搜索
          </button>
          {search && (
            <button
              onClick={() => { setSearch(''); setSearchInput(''); setPage(1) }}
              style={btnBase}
            >
              清除
            </button>
          )}
          <button onClick={() => { void fetchUsers() }} style={btnBase}>↻ 刷新</button>
        </div>
      </div>

      {/* Total info */}
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        共 <strong style={{ color: 'var(--text-secondary)' }}>{total}</strong> 位用户
        {search && <span>，搜索：&ldquo;{search}&rdquo;</span>}
      </div>

      {/* Error */}
      {error && (
        <div style={{ fontSize: 13, color: '#ef4444', background: '#ef444415', padding: '8px 12px', borderRadius: 6 }}>
          ⚠️ {error}
        </div>
      )}

      {/* Table container */}
      <div style={{ flex: 1, overflowX: 'auto', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 12 }}>
        {loading ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
            加载中…
          </div>
        ) : users.length === 0 ? (
          <div style={{ padding: 64, textAlign: 'center', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>👤</div>
            <div style={{ fontSize: 14 }}>{search ? '没有找到匹配的用户' : '暂无用户数据'}</div>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: 160 }} />
              <col style={{ width: 180 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 260 }} />
            </colgroup>
            <thead>
              <tr style={{ background: 'var(--bg-input)' }}>
                {['用户名', '邮箱', '登录方式', 'Soul Coin', '居民数', '注册时间', '状态', '操作'].map((col) => (
                  <th
                    key={col}
                    style={{
                      padding: '10px 14px',
                      fontSize: 12,
                      fontWeight: 600,
                      color: 'var(--text-muted)',
                      textAlign: col === 'Soul Coin' ? 'right' : col === '登录方式' || col === '居民数' || col === '状态' ? 'center' : 'left',
                      borderBottom: '1px solid var(--border)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <UserRow
                  key={user.id}
                  user={user}
                  onAdjustCoin={setAdjustTarget}
                  onToggleBan={(u) => { void handleToggleBan(u) }}
                  onToggleAdmin={(u) => { void handleToggleAdmin(u) }}
                  actionLoading={actionLoading}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {!loading && users.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            第 {page} / {totalPages} 页，每页 {perPage} 条
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={() => setPage(1)}
              disabled={page <= 1}
              style={{ ...btnBase, opacity: page <= 1 ? 0.4 : 1, cursor: page <= 1 ? 'default' : 'pointer' }}
            >
              «
            </button>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              style={{ ...btnBase, opacity: page <= 1 ? 0.4 : 1, cursor: page <= 1 ? 'default' : 'pointer' }}
            >
              ‹ 上一页
            </button>

            {/* Page numbers around current */}
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const start = Math.max(1, Math.min(page - 2, totalPages - 4))
              return start + i
            }).map((p) => (
              <button
                key={p}
                onClick={() => setPage(p)}
                style={{
                  ...btnBase,
                  minWidth: 32,
                  padding: '6px 8px',
                  background: p === page ? 'var(--accent-blue)' : 'var(--bg-input)',
                  color: p === page ? 'white' : 'var(--text-secondary)',
                  border: p === page ? 'none' : '1px solid var(--border)',
                  fontWeight: p === page ? 700 : 400,
                }}
              >
                {p}
              </button>
            ))}

            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              style={{ ...btnBase, opacity: page >= totalPages ? 0.4 : 1, cursor: page >= totalPages ? 'default' : 'pointer' }}
            >
              下一页 ›
            </button>
            <button
              onClick={() => setPage(totalPages)}
              disabled={page >= totalPages}
              style={{ ...btnBase, opacity: page >= totalPages ? 0.4 : 1, cursor: page >= totalPages ? 'default' : 'pointer' }}
            >
              »
            </button>
          </div>
        </div>
      )}

      {/* Adjust coin modal */}
      {adjustTarget && (
        <AdjustCoinModal
          user={adjustTarget}
          onClose={() => setAdjustTarget(null)}
          onSuccess={(balance) => handleAdjustCoinSuccess(adjustTarget.id, balance)}
        />
      )}
    </div>
  )
}
