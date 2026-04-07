import Phaser from 'phaser'
import { bridge } from './phaserBridge'
import { applyStatusVisuals, STATUS_CONFIG } from './StatusVisuals'
import { useGameStore } from '../stores/gameStore'
import { sendPosition } from '../services/ws'

const TILE_SIZE = 32
const PLAYER_SPEED = 160
const NPC_INTERACT_DISTANCE = 60

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
  private residents: ResidentData[] = []
  private mapReady = false
  private otherPlayerSprites: Map<string, Phaser.GameObjects.Text> = new Map()

  preload() {
    const base = '/assets/village/tilemap/'
    for (const [key, filename] of Object.entries(TILESET_IMAGE_MAP)) {
      this.load.image(key, base + filename)
    }
    this.load.tilemapTiledJSON('map', base + 'tilemap.json')
    this.load.atlas(
      'player_atlas',
      '/assets/village/agents/埃迪/texture.png',
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

    // Player
    this.player = this.physics.add.sprite(76 * TILE_SIZE, 50 * TILE_SIZE, 'player_atlas', 'down')
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

      this.add.text(x, y - 32, r.name, {
        fontSize: '13px',
        color: '#ffffff',
        backgroundColor: '#18181bcc',
        padding: { x: 6, y: 2 },
      }).setOrigin(0.5).setDepth(3)

      this.npcSprites.push(sprite)
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

    this.mapReady = true
  }

  update() {
    if (!this.mapReady || !this.player?.body) return

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

    // Render/update other players (as simple name labels for MVP)
    const onlinePlayers = useGameStore.getState().onlinePlayers
    onlinePlayers.forEach((p, playerId) => {
      if (!this.otherPlayerSprites.has(playerId)) {
        const label = this.add.text(p.x, p.y - 20, p.name, {
          fontSize: '11px', color: '#0ea5e9',
          backgroundColor: '#0ea5e920', padding: { x: 4, y: 2 },
        }).setDepth(5)
        this.otherPlayerSprites.set(playerId, label)
      } else {
        const label = this.otherPlayerSprites.get(playerId)!
        label.setPosition(p.x, p.y - 20)
      }
    })
    // Remove disconnected players
    this.otherPlayerSprites.forEach((label, playerId) => {
      if (!onlinePlayers.has(playerId)) {
        label.destroy()
        this.otherPlayerSprites.delete(playerId)
      }
    })

    // NPC proximity
    let nearest: ResidentData | null = null
    let nearestDist = Infinity
    for (const npc of this.npcSprites) {
      const dist = Phaser.Math.Distance.Between(this.player.x, this.player.y, npc.x, npc.y)
      if (dist < NPC_INTERACT_DISTANCE && dist < nearestDist) {
        nearestDist = dist
        nearest = (npc as unknown as Record<string, unknown>).__residentData as ResidentData
      }
    }
    bridge.emit('npc:nearby', nearest)

    if (Phaser.Input.Keyboard.JustDown(this.eKey) && nearest) {
      const cfg = STATUS_CONFIG[nearest.status]
      if (cfg?.canChat) {
        bridge.emit('npc:interact', nearest)
      }
    }
  }
}
