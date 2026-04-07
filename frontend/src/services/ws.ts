import { useGameStore } from '../stores/gameStore'

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
const wsListeners = new Set<(data: Record<string, unknown>) => void>()
// Queue important messages that arrive before any listener is registered (e.g. daily_reward)
const earlyMessageQueue: Record<string, unknown>[] = []
const QUEUED_TYPES = new Set(['daily_reward', 'coin_earned'])

export function connectWS(): void {
  const token = useGameStore.getState().token
  if (!token || socket?.readyState === WebSocket.OPEN) return

  const API_WS = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/^http/, 'ws')
  socket = new WebSocket(`${API_WS}/ws?token=${token}`)

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data as string) as Record<string, unknown>
      if (data.type === 'coin_update' && typeof data.balance === 'number') {
        useGameStore.getState().updateBalance(data.balance)
      }
      // Handle online players
      if (data.type === 'player_moved') {
        useGameStore.getState().setOnlinePlayer({
          player_id: data.player_id as string,
          name: (data.name as string) || '?',
          x: data.x as number,
          y: data.y as number,
          direction: (data.direction as string) || 'down',
        })
      }
      if (data.type === 'player_joined') {
        useGameStore.getState().setOnlinePlayer({
          player_id: data.player_id as string,
          name: (data.name as string) || '?',
          x: (data.x as number) ?? 0,
          y: (data.y as number) ?? 0,
          direction: (data.direction as string) || 'down',
        })
      }
      if (data.type === 'player_left') {
        useGameStore.getState().removeOnlinePlayer(data.player_id as string)
      }
      if (data.type === 'online_players') {
        const players = data.players as Array<Record<string, unknown>>
        players.forEach((p) => useGameStore.getState().setOnlinePlayer({
          player_id: p.player_id as string,
          name: (p.name as string) || '?',
          x: p.x as number,
          y: p.y as number,
          direction: (p.direction as string) || 'down',
        }))
      }
      // If no listeners registered yet, queue important messages for replay
      if (wsListeners.size === 0 && QUEUED_TYPES.has(data.type as string)) {
        earlyMessageQueue.push(data)
      } else {
        wsListeners.forEach((cb) => cb(data))
      }
    } catch {
      // ignore malformed messages
    }
  }

  socket.onclose = () => {
    socket = null
    useGameStore.getState().clearOnlinePlayers()
    reconnectTimer = setTimeout(connectWS, 3000)
  }

  socket.onerror = () => {
    socket?.close()
  }
}

export function onWSMessage(cb: (data: Record<string, unknown>) => void): () => void {
  wsListeners.add(cb)
  // Replay any messages that arrived before this listener was registered
  if (earlyMessageQueue.length > 0) {
    const queued = [...earlyMessageQueue]
    earlyMessageQueue.length = 0
    queued.forEach((msg) => cb(msg))
  }
  return () => wsListeners.delete(cb)
}

export function sendWS(data: Record<string, unknown>): void {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(data))
  }
}

export function disconnectWS(): void {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  socket?.close()
  socket = null
}

let lastSentX = -1
let lastSentY = -1

export function sendPosition(x: number, y: number, direction: string): void {
  // Only send if moved more than 4px
  if (Math.abs(x - lastSentX) < 4 && Math.abs(y - lastSentY) < 4) return
  lastSentX = x
  lastSentY = y
  sendWS({ type: 'move', x: Math.round(x), y: Math.round(y), direction })
}
