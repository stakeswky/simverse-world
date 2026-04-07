import { useGameStore } from '../stores/gameStore'

let socket: WebSocket | null = null
const wsListeners = new Set<(data: Record<string, unknown>) => void>()

export function connectWS(): void {
  const token = useGameStore.getState().token
  if (!token || socket?.readyState === WebSocket.OPEN) return

  const API_WS = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/^http/, 'ws')
  socket = new WebSocket(`${API_WS}/ws?token=${token}`)

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data as string) as Record<string, unknown>
      // Handle coin updates centrally
      if (data.type === 'coin_update' && typeof data.balance === 'number') {
        useGameStore.getState().updateBalance(data.balance)
      }
      wsListeners.forEach((cb) => cb(data))
    } catch {
      // ignore malformed messages
    }
  }

  socket.onclose = () => {
    socket = null
    // Reconnect after 3 seconds (exponential backoff could be added later)
    setTimeout(connectWS, 3000)
  }

  socket.onerror = () => {
    socket?.close()
  }
}

export function onWSMessage(cb: (data: Record<string, unknown>) => void): () => void {
  wsListeners.add(cb)
  return () => wsListeners.delete(cb)
}

export function sendWS(data: Record<string, unknown>): void {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(data))
  }
}

export function disconnectWS(): void {
  socket?.close()
  socket = null
}
