import { create } from 'zustand'

interface User {
  id: string
  name: string
  email: string
  avatar: string | null
  soul_coin_balance: number
}

export interface OnlinePlayer {
  player_id: string
  name: string
  x: number
  y: number
  direction: string
}

interface GameState {
  user: User | null
  token: string | null
  chatOpen: boolean
  chatResident: { slug: string; name: string; role: string } | null
  inputFocused: boolean
  profileTab: 'residents' | 'conversations' | 'transactions' | 'settings'
  onlinePlayers: Map<string, OnlinePlayer>

  setAuth: (user: User, token: string) => void
  logout: () => void
  openChat: (resident: { slug: string; name: string; role: string }) => void
  closeChat: () => void
  setInputFocused: (v: boolean) => void
  updateBalance: (balance: number) => void
  setProfileTab: (tab: 'residents' | 'conversations' | 'transactions' | 'settings') => void
  setOnlinePlayer: (p: OnlinePlayer) => void
  removeOnlinePlayer: (id: string) => void
  clearOnlinePlayers: () => void
}

export const useGameStore = create<GameState>((set) => ({
  user: (() => { try { return JSON.parse(localStorage.getItem('user') || 'null') } catch { return null } })(),
  token: localStorage.getItem('token'),
  chatOpen: false,
  chatResident: null,
  inputFocused: false,
  profileTab: 'residents',
  onlinePlayers: new Map(),

  setAuth: (user, token) => {
    localStorage.setItem('token', token)
    localStorage.setItem('user', JSON.stringify(user))
    set({ user, token })
  },
  logout: () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    set({ user: null, token: null })
  },
  openChat: (resident) => set({ chatOpen: true, chatResident: resident }),
  closeChat: () => set({ chatOpen: false, chatResident: null, inputFocused: false }),
  setInputFocused: (v) => set({ inputFocused: v }),
  updateBalance: (balance) => set((s) => s.user ? { user: { ...s.user, soul_coin_balance: balance } } : {}),
  setProfileTab: (tab) => set({ profileTab: tab }),
  setOnlinePlayer: (p) => set((s) => {
    const next = new Map(s.onlinePlayers)
    next.set(p.player_id, p)
    return { onlinePlayers: next }
  }),
  removeOnlinePlayer: (id) => set((s) => {
    const next = new Map(s.onlinePlayers)
    next.delete(id)
    return { onlinePlayers: next }
  }),
  clearOnlinePlayers: () => set({ onlinePlayers: new Map() }),
}))
