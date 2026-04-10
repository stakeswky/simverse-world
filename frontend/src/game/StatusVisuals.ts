import Phaser from 'phaser'

export interface StatusConfig {
  label: string
  canChat: boolean
  bubble: string
  alpha: number
  tint: number | null
}

export const STATUS_CONFIG: Record<string, StatusConfig> = {
  idle:        { label: '🟢 空闲',  canChat: true,  bubble: '💭', alpha: 1.0, tint: null },
  sleeping:    { label: '💤 沉睡',  canChat: false, bubble: '💤', alpha: 0.5, tint: 0x8888cc },
  chatting:    { label: '💬 对话中', canChat: false, bubble: '💬', alpha: 1.0, tint: null },
  popular:     { label: '🔥 热门',  canChat: true,  bubble: '🔥', alpha: 1.0, tint: null },
  walking:     { label: '🚶 移动中', canChat: false, bubble: '🚶', alpha: 1.0, tint: null },
  socializing: { label: '🗣️ 交谈中', canChat: false, bubble: '🗣️', alpha: 1.0, tint: 0x22c55e },
}

const IDLE_THOUGHTS = ['💭', '☕', '🤔', '📖', '✨', '🎵']

/** Tracks all game objects created by applyStatusVisuals so they can be cleaned up */
const visualRegistry = new Map<Phaser.Physics.Arcade.Sprite, {
  objects: Phaser.GameObjects.GameObject[]
  timers: Phaser.Time.TimerEvent[]
}>()

/** Remove all visual effects previously applied to a sprite */
export function clearStatusVisuals(
  scene: Phaser.Scene,
  sprite: Phaser.Physics.Arcade.Sprite,
): void {
  scene.tweens.killTweensOf(sprite)
  sprite.setAlpha(1).clearTint().setAngle(0)

  const entry = visualRegistry.get(sprite)
  if (entry) {
    for (const obj of entry.objects) {
      scene.tweens.killTweensOf(obj)
      obj.destroy()
    }
    for (const timer of entry.timers) {
      timer.destroy()
    }
    visualRegistry.delete(sprite)
  }
}

export function applyStatusVisuals(
  scene: Phaser.Scene,
  sprite: Phaser.Physics.Arcade.Sprite,
  status: string,
  x: number,
  y: number,
): Phaser.GameObjects.Text {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.idle
  sprite.setAlpha(cfg.alpha)
  if (cfg.tint) sprite.setTint(cfg.tint)

  const objects: Phaser.GameObjects.GameObject[] = []
  const timers: Phaser.Time.TimerEvent[] = []

  if (status === 'idle') {
    scene.tweens.add({
      targets: sprite, scaleY: sprite.scaleY * 0.97,
      duration: 1800, yoyo: true, repeat: -1, ease: 'Sine.easeInOut',
    })
  } else if (status === 'sleeping') {
    scene.tweens.add({ targets: sprite, y: y + 3, duration: 2500, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
    scene.tweens.add({ targets: sprite, angle: 8, duration: 3000, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
  } else if (status === 'chatting') {
    scene.tweens.add({ targets: sprite, x: x - 2, duration: 300, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
  } else if (status === 'popular') {
    scene.tweens.add({
      targets: sprite,
      scaleX: sprite.scaleX * 1.03, scaleY: sprite.scaleY * 1.03,
      duration: 1200, yoyo: true, repeat: -1, ease: 'Sine.easeInOut',
    })
    const glow = scene.add.graphics().setDepth(0)
    glow.fillStyle(0xf59e0b, 0.08)
    glow.fillCircle(x, y, 35)
    glow.fillStyle(0xf59e0b, 0.05)
    glow.fillCircle(x, y, 50)
    scene.tweens.add({ targets: glow, alpha: 0.3, duration: 1500, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
    objects.push(glow)
  } else if (status === 'walking') {
    // Subtle horizontal bob while walking
    scene.tweens.add({
      targets: sprite, x: x + 2, duration: 200, yoyo: true, repeat: -1, ease: 'Linear',
    })
  } else if (status === 'socializing') {
    // Gentle bounce and green tint
    scene.tweens.add({
      targets: sprite,
      scaleY: sprite.scaleY * 1.05,
      duration: 600, yoyo: true, repeat: -1, ease: 'Sine.easeInOut',
    })
    const glow = scene.add.graphics().setDepth(0)
    glow.fillStyle(0x22c55e, 0.06)
    glow.fillCircle(x, y, 30)
    scene.tweens.add({ targets: glow, alpha: 0.2, duration: 1000, yoyo: true, repeat: -1 })
    objects.push(glow)
  }

  const bubbleText = scene.add.text(x + 20, y - 48, cfg.bubble, {
    fontSize: '16px',
    backgroundColor: '#18181bee',
    padding: { x: 4, y: 2 },
  }).setOrigin(0.5).setDepth(4)

  scene.tweens.add({
    targets: bubbleText, y: bubbleText.y - 4,
    duration: 2000, yoyo: true, repeat: -1, ease: 'Sine.easeInOut',
  })
  objects.push(bubbleText)

  if (status === 'idle') {
    let idx = 0
    timers.push(scene.time.addEvent({
      delay: 3000, loop: true,
      callback: () => { idx = (idx + 1) % IDLE_THOUGHTS.length; bubbleText.setText(IDLE_THOUGHTS[idx]) },
    }))
  } else if (status === 'sleeping') {
    const zzz = ['💤', '💤💤', '💤💤💤', '💤💤', '💤']
    let idx = 0
    timers.push(scene.time.addEvent({
      delay: 1500, loop: true,
      callback: () => { idx = (idx + 1) % zzz.length; bubbleText.setText(zzz[idx]) },
    }))
  }

  visualRegistry.set(sprite, { objects, timers })

  return bubbleText
}
