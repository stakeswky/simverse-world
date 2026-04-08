import { create } from 'zustand'

interface User {
  id: string
  name: string
  email: string
  avatar: string | null
  soul_coin_balance: number
  is_admin?: boolean
}

export interface OnlinePlayer {
  player_id: string
  name: string
  x: number
  y: number
  direction: string
}

export type ChatTarget =
  | { type: 'npc'; slug: string; name: string; role: string }
  | { type: 'player'; userId: string; name: string }

export interface PlayerChatMessage {
  from: string
  text: string
  isAuto: boolean
  timestamp: number
}

interface GameState {
  user: User | null
  token: string | null
  playerSpriteKey: string
  chatOpen: boolean
  chatResident: { slug: string; name: string; role: string } | null
  chatTarget: ChatTarget | null
  playerChatMessages: PlayerChatMessage[]
  inputFocused: boolean
  profileTab: 'residents' | 'conversations' | 'transactions' | 'settings'
  onlinePlayers: Map<string, OnlinePlayer>
  spawnX: number
  spawnY: number

  setAuth: (user: User, token: string) => void
  logout: () => void
  setPlayerSpriteKey: (key: string) => void
  openChat: (resident: { slug: string; name: string; role: string }) => void
  closeChat: () => void
  setChatTarget: (target: ChatTarget) => void
  clearChatTarget: () => void
  addPlayerChatMessage: (msg: PlayerChatMessage) => void
  setInputFocused: (v: boolean) => void
  updateBalance: (balance: number) => void
  setProfileTab: (tab: 'residents' | 'conversations' | 'transactions' | 'settings') => void
  setOnlinePlayer: (p: OnlinePlayer) => void
  removeOnlinePlayer: (id: string) => void
  clearOnlinePlayers: () => void
  setSpawnPosition: (x: number, y: number) => void
}

export const useGameStore = create<GameState>((set) => ({
  user: (() => { try { return JSON.parse(localStorage.getItem('user') || 'null') } catch { return null } })(),
  token: localStorage.getItem('token'),
  playerSpriteKey: '埃迪',
  chatOpen: false,
  chatResident: null,
  chatTarget: null,
  playerChatMessages: [],
  inputFocused: false,
  profileTab: 'residents',
  onlinePlayers: new Map(),
  spawnX: 76 * 32,
  spawnY: 50 * 32,

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
  setPlayerSpriteKey: (key) => set({ playerSpriteKey: key }),
  openChat: (resident) => set({ chatOpen: true, chatResident: resident }),
  closeChat: () => set({ chatOpen: false, chatResident: null, chatTarget: null, inputFocused: false }),
  setChatTarget: (target) => set({
    chatTarget: target,
    chatOpen: true,
    ...(target.type === 'player' ? { playerChatMessages: [] } : {}),
    ...(target.type === 'npc'
      ? { chatResident: { slug: target.slug, name: target.name, role: target.role } }
      : { chatResident: null }),
  }),
  clearChatTarget: () => set({ chatTarget: null, chatOpen: false, chatResident: null, inputFocused: false }),
  addPlayerChatMessage: (msg) => set((s) => ({ playerChatMessages: [...s.playerChatMessages, msg] })),
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
  setSpawnPosition: (x, y) => set({ spawnX: x, spawnY: y }),
}))
