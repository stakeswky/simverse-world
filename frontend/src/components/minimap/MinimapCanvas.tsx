import { useEffect, useRef } from 'react'
import { useGameStore } from '../../stores/gameStore'

const MAP_TILES_W = 140
const MAP_TILES_H = 100
const MINIMAP_W = 180
const MINIMAP_H = 130

export function MinimapCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const textureUrl = useGameStore((s) => s.minimapTextureUrl)
  const playerTileX = useGameStore((s) => s.playerTileX)
  const playerTileY = useGameStore((s) => s.playerTileY)
  const viewport = useGameStore((s) => s.cameraViewport)

  // Load texture image when URL changes
  useEffect(() => {
    if (!textureUrl) return
    const img = new Image()
    img.onload = () => { imgRef.current = img }
    img.src = textureUrl
  }, [textureUrl])

  // Redraw canvas on every relevant state change
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, MINIMAP_W, MINIMAP_H)

    // Draw cached map texture
    if (imgRef.current) {
      ctx.drawImage(imgRef.current, 0, 0, MINIMAP_W, MINIMAP_H)
    } else {
      // Fallback: dark green background
      ctx.fillStyle = '#2d5016'
      ctx.fillRect(0, 0, MINIMAP_W, MINIMAP_H)
    }

    // Draw camera viewport rectangle
    if (viewport) {
      const vx = (viewport.x / MAP_TILES_W) * MINIMAP_W
      const vy = (viewport.y / MAP_TILES_H) * MINIMAP_H
      const vw = (viewport.w / MAP_TILES_W) * MINIMAP_W
      const vh = (viewport.h / MAP_TILES_H) * MINIMAP_H
      ctx.strokeStyle = 'rgba(255,255,255,0.5)'
      ctx.lineWidth = 1
      ctx.strokeRect(vx, vy, vw, vh)
    }

    // Draw player dot
    const px = (playerTileX / MAP_TILES_W) * MINIMAP_W
    const py = (playerTileY / MAP_TILES_H) * MINIMAP_H
    ctx.beginPath()
    ctx.arc(px, py, 4, 0, Math.PI * 2)
    ctx.fillStyle = '#ffffff'
    ctx.fill()
    ctx.strokeStyle = '#3b82f6'
    ctx.lineWidth = 2
    ctx.stroke()
  }, [playerTileX, playerTileY, viewport, textureUrl])

  return (
    <canvas
      ref={canvasRef}
      width={MINIMAP_W}
      height={MINIMAP_H}
      style={{ display: 'block', borderRadius: 6 }}
    />
  )
}
