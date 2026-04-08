type EventCallback = (...args: unknown[]) => void

class PhaserBridge {
  private listeners = new Map<string, Set<EventCallback>>()

  on(event: string, cb: EventCallback): () => void {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set())
    this.listeners.get(event)!.add(cb)
    return () => this.listeners.get(event)?.delete(cb)
  }

  emit(event: string, ...args: unknown[]): void {
    this.listeners.get(event)?.forEach((cb) => cb(...args))
  }
}

export const bridge = new PhaserBridge()

// Events emitted from Phaser:
// "npc:nearby"      -> ResidentData | null                            (when player walks near/away from NPC)
// "npc:interact"    -> ResidentData                                   (when player presses E on NPC)
// "player:nearby"   -> { userId: string; name: string; x: number; y: number } | null  (when player walks near/away from online player)
// "player:interact" -> { userId: string; name: string; x: number; y: number }         (when player presses E near online player)
