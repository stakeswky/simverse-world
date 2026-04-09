import Phaser from 'phaser'
import { bridge } from './phaserBridge'
import { applyStatusVisuals, STATUS_CONFIG } from './StatusVisuals'
import { useGameStore } from '../stores/gameStore'
import { sendPosition, sendWS, onWSMessage } from '../services/ws'

const TILE_SIZE = 32
const PLAYER_SPEED = 160
const NPC_INTERACT_DISTANCE = 60
const PLAYER_INTERACT_DISTANCE = 80

const TILESET_IMAGE_MAP: Record<string, string> = {
  blocks_1: 'blocks_1.png',
  walls: 'Room_Builder_32x32.png',
  interiors_pt1: 'interiors_pt1.png',
  interiors_pt2: 'interiors_pt2.png',
  interiors_pt3: 'interiors_pt3.png',
  interiors_pt4: 'interiors_pt4.png',
  interiors_pt5: 'interiors_pt5.png',
  CuteRPG_Field_B: 'CuteRPG_Field_B.png',
  CuteRPG_Field_C: 'CuteRPG_Field_C.png',
  CuteRPG_Harbor_C: 'CuteRPG_Harbor_C.png',
  CuteRPG_Village_B: 'CuteRPG_Village_B.png',
  CuteRPG_Forest_B: 'CuteRPG_Forest_B.png',
  CuteRPG_Desert_C: 'CuteRPG_Desert_C.png',
  CuteRPG_Mountains_B: 'CuteRPG_Mountains_B.png',
  CuteRPG_Desert_B: 'CuteRPG_Desert_B.png',
  CuteRPG_Forest_C: 'CuteRPG_Forest_C.png',
}

export interface ResidentData {
  slug: string
  name: string
  status: string
  sprite_key: string
  tile_x: number
  tile_y: number
  district: string
  meta_json: { role?: string }
  token_cost_per_turn: number
  star_rating: number
  heat: number
}

let gameInstance: Phaser.Game | null = null

export function destroyGame(): void {
  if (gameInstance) {
    gameInstance.destroy(true)
    gameInstance = null
  }
}

export function initGame(container: HTMLElement): void {
  if (gameInstance) return
  const zoom = Math.max(1, window.innerWidth / 4400)
  gameInstance = new Phaser.Game({
    type: Phaser.AUTO,
    width: container.clientWidth / zoom,
    height: container.clientHeight / zoom,
    parent: container,
    pixelArt: true,
    physics: { default: 'arcade', arcade: { gravity: { x: 0, y: 0 } } },
    scene: [MainScene],
    scale: { zoom },
  })
}

class MainScene extends Phaser.Scene {
  private player!: Phaser.Physics.Arcade.Sprite
  private cursors!: Phaser.Types.Input.Keyboard.CursorKeys
  private wasd!: { up: Phaser.Input.Keyboard.Key; down: Phaser.Input.Keyboard.Key; left: Phaser.Input.Keyboard.Key; right: Phaser.Input.Keyboard.Key }
  private eKey!: Phaser.Input.Keyboard.Key
  private npcSprites: Phaser.Physics.Arcade.Sprite[] = []
  private npcLabels: Phaser.GameObjects.Text[] = []
  private residents: ResidentData[] = []
  private mapReady = false
  private isTeleporting = false
  private otherPlayerSprites: Map<string, { sprite: Phaser.Physics.Arcade.Sprite; label: Phaser.GameObjects.Text }> = new Map()

  preload() {
    const base = '/assets/village/tilemap/'
    for (const [key, filename] of Object.entries(TILESET_IMAGE_MAP)) {
      this.load.image(key, base + filename)
    }
    this.load.tilemapTiledJSON('map', base + 'tilemap.json')

    const spriteKey = useGameStore.getState().playerSpriteKey
    this.load.atlas(
      'player_atlas',
      `/assets/village/agents/${spriteKey}/texture.png`,
      '/assets/village/agents/sprite.json',
    )
  }

  async create() {
    const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
    try {
      const resp = await fetch(`${API}/residents`)
      this.residents = resp.ok ? (await resp.json() as ResidentData[]) : []
    } catch {
      this.residents = []
    }

    // Load resident sprites
    const spritesToLoad: string[] = []
    for (const r of this.residents) {
      if (!this.textures.exists(r.sprite_key)) {
        spritesToLoad.push(r.sprite_key)
        this.load.atlas(
          r.sprite_key,
          `/assets/village/agents/${r.sprite_key}/texture.png`,
          '/assets/village/agents/sprite.json',
        )
      }
    }

    if (spritesToLoad.length > 0 && !this.load.isLoading()) {
      this.load.start()
      await new Promise<void>((resolve) => this.load.once('complete', resolve))
    }

    this.setupWorld()
  }

  private generateMinimapTexture(): void {
    const cam = this.cameras.main
    const origScrollX = cam.scrollX
    const origScrollY = cam.scrollY
    const origZoom = cam.zoom

    // Temporarily zoom out to capture entire map
    const mapW = cam.getBounds().width
    const mapH = cam.getBounds().height
    const zoom = Math.min(cam.width / mapW, cam.height / mapH)

    cam.setZoom(zoom)
    cam.setScroll(0, 0)
    cam.stopFollow()

    // Wait one frame for the camera to render, then snapshot
    this.time.delayedCall(50, () => {
      this.game.renderer.snapshotArea(
        0, 0,
        Math.ceil(mapW * zoom),
        Math.ceil(mapH * zoom),
        (image) => {
          // Restore camera
          cam.setZoom(origZoom)
          cam.setScroll(origScrollX, origScrollY)
          if (this.player) {
            cam.startFollow(this.player, true, 0.1, 0.1)
          }

          const img = image as HTMLImageElement
          if (img.src) {
            useGameStore.getState().setMinimapTexture(img.src)
          }
        }
      )
    })
  }

  private setupWorld() {
    const map = this.make.tilemap({ key: 'map' })

    const tilesetMap: Record<string, Phaser.Tilemaps.Tileset | null> = {}
    for (const key of Object.keys(TILESET_IMAGE_MAP)) {
      const tiled_name = key === 'walls' ? 'Room_Builder_32x32' : key === 'blocks_1' ? 'blocks' : key
      tilesetMap[key] = map.addTilesetImage(tiled_name, key)
    }

    const allTilesets = Object.entries(tilesetMap)
      .filter(([k, v]) => k !== 'blocks_1' && v !== null)  // blocks_1 is collision-only, not rendered
      .map(([, v]) => v!) as Phaser.Tilemaps.Tileset[]

    const layerNames = [
      'Bottom Ground', 'Exterior Ground', 'Exterior Decoration L1', 'Exterior Decoration L2',
      'Interior Ground', 'Interior Furniture L1', 'Interior Furniture L2 ',
      'Foreground L1', 'Foreground L2',
    ]
    for (const name of layerNames) {
      const layer = map.createLayer(name, name === 'Wall' ? [tilesetMap.CuteRPG_Field_C!, tilesetMap.walls!] : allTilesets, 0, 0)
      if (name.startsWith('Foreground')) layer?.setDepth(2)
    }

    // Wall layer separately
    const wallLayer = map.createLayer('Wall', [tilesetMap.CuteRPG_Field_C!, tilesetMap.walls!].filter(Boolean) as Phaser.Tilemaps.Tileset[], 0, 0)
    wallLayer?.setDepth(1)

    const collisionLayer = map.createLayer('Collisions', tilesetMap.blocks_1!, 0, 0)
    collisionLayer?.setCollisionByExclusion([-1])
    collisionLayer?.setVisible(false)

    // Player — use spawn position from store (set by backend spawn_position message)
    const { spawnX, spawnY } = useGameStore.getState()
    this.player = this.physics.add.sprite(spawnX, spawnY, 'player_atlas', 'down')
      .setSize(24, 24).setOffset(4, 8).setDepth(1)
    this.player.displayWidth = 40
    this.player.scaleY = this.player.scaleX

    if (collisionLayer) {
      this.physics.add.collider(this.player, collisionLayer)
    }

    for (const dir of ['left', 'right', 'down', 'up']) {
      this.anims.create({
        key: `player-${dir}-walk`,
        frames: this.anims.generateFrameNames('player_atlas', {
          prefix: `${dir}-walk.`, start: 0, end: 3, zeroPad: 3,
        }),
        frameRate: 8,
        repeat: -1,
      })
    }

    // NPCs
    for (const r of this.residents) {
      const x = r.tile_x * TILE_SIZE + TILE_SIZE / 2
      const y = r.tile_y * TILE_SIZE + TILE_SIZE

      const sprite = this.physics.add.sprite(x, y, r.sprite_key, 'down')
        .setSize(24, 24).setOffset(4, 8).setDepth(1).setImmovable(true)
      sprite.displayWidth = 40
      sprite.scaleY = sprite.scaleX
      ;(sprite as unknown as Record<string, unknown>).__residentData = r

      applyStatusVisuals(this, sprite, r.status, x, y)

      const label = this.add.text(x, y - 32, r.name, {
        fontSize: '13px',
        color: '#ffffff',
        backgroundColor: '#18181bcc',
        padding: { x: 6, y: 2 },
      }).setOrigin(0.5).setDepth(3).setAlpha(0.3)

      this.npcSprites.push(sprite)
      this.npcLabels.push(label)
    }

    // Camera
    this.cameras.main.startFollow(this.player, true, 0.1, 0.1)
    this.cameras.main.setBounds(0, 0, map.widthInPixels, map.heightInPixels)

    // Input
    this.cursors = this.input.keyboard!.createCursorKeys()
    this.wasd = this.input.keyboard!.addKeys({
      up: Phaser.Input.Keyboard.KeyCodes.W,
      down: Phaser.Input.Keyboard.KeyCodes.S,
      left: Phaser.Input.Keyboard.KeyCodes.A,
      right: Phaser.Input.Keyboard.KeyCodes.D,
    }) as { up: Phaser.Input.Keyboard.Key; down: Phaser.Input.Keyboard.Key; left: Phaser.Input.Keyboard.Key; right: Phaser.Input.Keyboard.Key }
    this.eKey = this.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.E)

    // Handle late-arriving spawn_position (WS connected after scene creation)
    onWSMessage((msg) => {
      if (msg.type === 'spawn_position' && this.player) {
        const x = msg.x as number
        const y = msg.y as number
        this.player.setPosition(x, y)
        this.cameras.main.centerOn(x, y)
      }
    })

    // Listen for camera pan requests from React UI (search, bulletin board)
    bridge.on('camera:pan', (data: unknown) => {
      const { tile_x, tile_y } = data as { tile_x: number; tile_y: number }
      const targetX = tile_x * TILE_SIZE + TILE_SIZE / 2
      const targetY = tile_y * TILE_SIZE + TILE_SIZE
      this.cameras.main.pan(targetX, targetY, 600, 'Power2')
      // Move player to the target location
      this.player.setPosition(targetX, targetY)
    })

    bridge.on('minimap:teleport', (data: unknown) => {
      const { tileX, tileY } = data as { tileX: number; tileY: number; residentSlug?: string }
      this.teleportTo(tileX, tileY)
    })

    this.mapReady = true

    // Generate minimap texture after world is set up
    this.time.delayedCall(500, () => this.generateMinimapTexture())
  }

  private teleportTo(tileX: number, tileY: number): void {
    if (this.isTeleporting) return
    this.isTeleporting = true

    const cam = this.cameras.main
    const targetX = tileX * TILE_SIZE + TILE_SIZE / 2
    const targetY = tileY * TILE_SIZE + TILE_SIZE

    // Phase 1: Fade out (300ms)
    cam.fadeOut(300, 0, 0, 0)

    cam.once('camerafadeoutcomplete', () => {
      // Phase 2: Instant teleport — stop follow to prevent camera snap-back
      cam.stopFollow()
      this.player.setPosition(targetX, targetY)
      ;(this.player.body as Phaser.Physics.Arcade.Body).reset(targetX, targetY)
      cam.centerOn(targetX, targetY)
      // Restore follow after position is set
      cam.startFollow(this.player, true, 0.1, 0.1)

      // Phase 3: Fade in (500ms)
      cam.fadeIn(500, 0, 0, 0)

      cam.once('camerafadeincomplete', () => {
        this.isTeleporting = false
        // Persist teleported position to backend (bypass 4px dead-zone)
        sendWS({ type: 'move', x: Math.round(targetX), y: Math.round(targetY), direction: 'down' })
        bridge.emit('teleport:complete', { tileX, tileY })
      })
    })
  }

  update() {
    if (!this.mapReady || !this.player?.body) return
    if (this.isTeleporting) return

    // Pause movement when chat input is focused
    if (useGameStore.getState().inputFocused) {
      (this.player.body as Phaser.Physics.Arcade.Body).setVelocity(0, 0)
      this.player.anims.stop()
      return
    }

    const body = this.player.body as Phaser.Physics.Arcade.Body
    body.setVelocity(0, 0)

    const left = this.cursors.left.isDown || this.wasd.left.isDown
    const right = this.cursors.right.isDown || this.wasd.right.isDown
    const up = this.cursors.up.isDown || this.wasd.up.isDown
    const down = this.cursors.down.isDown || this.wasd.down.isDown

    // Allow both axes for diagonal movement
    if (left) body.setVelocityX(-PLAYER_SPEED)
    else if (right) body.setVelocityX(PLAYER_SPEED)

    if (up) body.setVelocityY(-PLAYER_SPEED)
    else if (down) body.setVelocityY(PLAYER_SPEED)

    // Normalize diagonal speed so it doesn't exceed PLAYER_SPEED
    if (body.velocity.length() > 0) {
      body.velocity.normalize().scale(PLAYER_SPEED)
    }

    // Determine animation direction (priority: horizontal > vertical)
    const moving = left || right || up || down
    if (!moving) {
      this.player.anims.stop()
    } else if (left) {
      this.player.anims.play('player-left-walk', true)
    } else if (right) {
      this.player.anims.play('player-right-walk', true)
    } else if (up) {
      this.player.anims.play('player-up-walk', true)
    } else if (down) {
      this.player.anims.play('player-down-walk', true)
    }

    // Broadcast player position when moving
    if (left || right || up || down) {
      const dir = left ? 'left' : right ? 'right' : up ? 'up' : 'down'
      sendPosition(this.player.x, this.player.y, dir)
    }

    // Broadcast player tile position for minimap
    const tileX = Math.floor(this.player.x / TILE_SIZE)
    const tileY = Math.floor(this.player.y / TILE_SIZE)
    const store = useGameStore.getState()
    if (tileX !== store.playerTileX || tileY !== store.playerTileY) {
      store.setPlayerTile(tileX, tileY)
    }

    // Broadcast camera viewport for minimap
    const cam = this.cameras.main
    store.setCameraViewport({
      x: cam.scrollX / TILE_SIZE,
      y: cam.scrollY / TILE_SIZE,
      w: cam.width / cam.zoom / TILE_SIZE,
      h: cam.height / cam.zoom / TILE_SIZE,
    })

    // Render/update other players as sprites with name labels
    const onlinePlayers = useGameStore.getState().onlinePlayers
    onlinePlayers.forEach((p, playerId) => {
      if (!this.otherPlayerSprites.has(playerId)) {
        // Create sprite using shared player_atlas
        const sprite = this.physics.add.sprite(p.x, p.y, 'player_atlas', p.direction || 'down')
          .setSize(24, 24).setOffset(4, 8).setDepth(1)
        sprite.displayWidth = 40
        sprite.scaleY = sprite.scaleX
        // Tint to distinguish from local player
        sprite.setTint(0x88ccff)

        const label = this.add.text(p.x, p.y - 28, p.name, {
          fontSize: '11px', color: '#ffffff',
          backgroundColor: '#0ea5e9cc', padding: { x: 4, y: 2 },
        }).setOrigin(0.5).setDepth(5)

        this.otherPlayerSprites.set(playerId, { sprite, label })
      }

      const entry = this.otherPlayerSprites.get(playerId)!
      const { sprite, label } = entry

      // Smoothly move toward target position
      const dx = p.x - sprite.x
      const dy = p.y - sprite.y
      const dist = Math.sqrt(dx * dx + dy * dy)

      if (dist > 2) {
        sprite.setPosition(sprite.x + dx * 0.3, sprite.y + dy * 0.3)
        // Play walk animation based on direction
        const animKey = `player-${p.direction}-walk`
        if (sprite.anims.currentAnim?.key !== animKey) {
          sprite.anims.play(animKey, true)
        }
      } else {
        sprite.setPosition(p.x, p.y)
        sprite.anims.stop()
        sprite.setFrame(p.direction || 'down')
      }

      label.setPosition(sprite.x, sprite.y - 28)
    })
    // Remove disconnected players
    this.otherPlayerSprites.forEach((entry, playerId) => {
      if (!onlinePlayers.has(playerId)) {
        entry.sprite.destroy()
        entry.label.destroy()
        this.otherPlayerSprites.delete(playerId)
      }
    })

    // NPC proximity
    let nearest: ResidentData | null = null
    let nearestDist = Infinity
    let nearestIndex = -1
    for (let i = 0; i < this.npcSprites.length; i++) {
      const npc = this.npcSprites[i]
      const dist = Phaser.Math.Distance.Between(this.player.x, this.player.y, npc.x, npc.y)
      if (dist < NPC_INTERACT_DISTANCE && dist < nearestDist) {
        nearestDist = dist
        nearest = (npc as unknown as Record<string, unknown>).__residentData as ResidentData
        nearestIndex = i
      }
    }
    // Update label visibility: highlight only the nearest NPC's label
    for (let i = 0; i < this.npcLabels.length; i++) {
      this.npcLabels[i].setAlpha(i === nearestIndex ? 1 : 0.3)
    }
    bridge.emit('npc:nearby', nearest)

    if (Phaser.Input.Keyboard.JustDown(this.eKey) && nearest) {
      const cfg = STATUS_CONFIG[nearest.status]
      if (cfg?.canChat) {
        bridge.emit('npc:interact', nearest)
      } else if (nearest.status === 'sleeping') {
        bridge.emit('npc:interact', nearest) // ChatDrawer handles wake confirmation
      } else if (nearest.status === 'chatting') {
        bridge.emit('npc:interact', nearest) // ChatDrawer handles queueing
      }
    }

    // Other player proximity
    let nearestPlayer: { userId: string; name: string; x: number; y: number } | null = null
    let nearestPlayerDist = Infinity
    this.otherPlayerSprites.forEach(({ sprite }, playerId) => {
      const dist = Phaser.Math.Distance.Between(this.player.x, this.player.y, sprite.x, sprite.y)
      if (dist < PLAYER_INTERACT_DISTANCE && dist < nearestPlayerDist) {
        nearestPlayerDist = dist
        const p = onlinePlayers.get(playerId)
        if (p) {
          nearestPlayer = { userId: playerId, name: p.name, x: sprite.x, y: sprite.y }
        }
      }
    })
    bridge.emit('player:nearby', nearestPlayer)

    if (Phaser.Input.Keyboard.JustDown(this.eKey) && nearestPlayer && !nearest) {
      bridge.emit('player:interact', nearestPlayer)
    }
  }
}
