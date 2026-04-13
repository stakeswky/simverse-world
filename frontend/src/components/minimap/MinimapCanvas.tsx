import { useEffect, useRef } from 'react'
import { useGameStore } from '../../stores/gameStore'

const MAP_TILES_W = 140
const MAP_TILES_H = 100

interface Props {
  width?: number
  height?: number
}

export function MinimapCanvas({ width = 180, height = 130 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const textureUrl = useGameStore((s) => s.minimapTextureUrl)
  const playerTileX = useGameStore((s) => s.playerTileX)
  const playerTileY = useGameStore((s) => s.playerTileY)
  const viewport = useGameStore((s) => s.cameraViewport)

  useEffect(() => {
    if (!textureUrl) return
    const img = new Image()
    img.onload = () => { imgRef.current = img }
    img.src = textureUrl
  }, [textureUrl])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, width, height)

    if (imgRef.current) {
      ctx.drawImage(imgRef.current, 0, 0, width, height)
    } else {
      ctx.fillStyle = '#2d5016'
      ctx.fillRect(0, 0, width, height)
    }

    if (viewport) {
      const vx = (viewport.x / MAP_TILES_W) * width
      const vy = (viewport.y / MAP_TILES_H) * height
      const vw = (viewport.w / MAP_TILES_W) * width
      const vh = (viewport.h / MAP_TILES_H) * height
      ctx.strokeStyle = 'rgba(255,255,255,0.5)'
      ctx.lineWidth = 1
      ctx.strokeRect(vx, vy, vw, vh)
    }

    const dotRadius = width > 200 ? 6 : 4
    const px = (playerTileX / MAP_TILES_W) * width
    const py = (playerTileY / MAP_TILES_H) * height
    ctx.beginPath()
    ctx.arc(px, py, dotRadius, 0, Math.PI * 2)
    ctx.fillStyle = '#ffffff'
    ctx.fill()
    ctx.strokeStyle = '#3b82f6'
    ctx.lineWidth = 2
    ctx.stroke()
  }, [playerTileX, playerTileY, viewport, textureUrl, width, height])

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{ display: 'block', borderRadius: width > 200 ? 10 : 6, pointerEvents: 'none' }}
    />
  )
}
