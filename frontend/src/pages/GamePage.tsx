import { useEffect, useRef } from 'react'
import { TopNav } from '../components/TopNav'
import { ChatDrawer } from '../components/ChatDrawer'
import { NpcTooltip } from '../components/NpcTooltip'
import { useGameStore } from '../stores/gameStore'

export function GamePage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const chatOpen = useGameStore((s) => s.chatOpen)

  useEffect(() => {
    import('../game/GameScene').then(({ initGame }) => {
      if (containerRef.current) {
        initGame(containerRef.current)
      }
    })
  }, [])

  return (
    <>
      <TopNav />
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
    </>
  )
}
