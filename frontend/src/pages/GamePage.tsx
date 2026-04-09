import { useEffect, useRef } from 'react'
import { TopNav } from '../components/TopNav'
import { ChatDrawer } from '../components/ChatDrawer'
import { NpcTooltip } from '../components/NpcTooltip'
import { BulletinBoard } from '../components/BulletinBoard'
import { CoinNotification } from '../components/CoinNotification'
import { MinimapOverlay } from '../components/minimap/MinimapOverlay'
import { useGameStore } from '../stores/gameStore'
import { connectWS, disconnectWS } from '../services/ws'
import { getSettings } from '../services/api'
import { bridge } from '../game/phaserBridge'

export function GamePage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const chatOpen = useGameStore((s) => s.chatOpen)

  useEffect(() => {
    let destroyed = false
    connectWS()

    const startGame = async () => {
      // Fetch player sprite key before initialising the Phaser game so that
      // GameScene.preload() can read it synchronously from the store.
      try {
        const settings = await getSettings()
        if (settings.character?.sprite_key) {
          useGameStore.getState().setPlayerSpriteKey(settings.character.sprite_key)
        }
      } catch {
        // Keep default sprite key on failure
      }

      const { initGame } = await import('../game/GameScene')
      if (!destroyed && containerRef.current) {
        initGame(containerRef.current)
      }
    }

    startGame()

    // Listen for player interact events from the Phaser game scene
    const unsubPlayerInteract = bridge.on('player:interact', (data) => {
      const { userId, name } = data as { userId: string; name: string; x: number; y: number }
      useGameStore.getState().setChatTarget({ type: 'player', userId, name })
    })

    return () => {
      destroyed = true
      unsubPlayerInteract()
      disconnectWS()
      import('../game/GameScene').then(({ destroyGame }) => destroyGame())
    }
  }, [])

  return (
    <>
      <TopNav />
      <MinimapOverlay />
      <div
        ref={containerRef}
        id="game-container"
        style={{
          position: 'fixed', top: 48, left: 0, bottom: 0,
          right: chatOpen ? 380 : 0,
          transition: 'right 0.3s ease',
        }}
      />
      <NpcTooltip />
      <ChatDrawer />
      <BulletinBoard />
      <CoinNotification />
    </>
  )
}
