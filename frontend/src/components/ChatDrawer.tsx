import { useEffect, useRef, useState } from 'react'
import { bridge } from '../game/phaserBridge'
import { useGameStore } from '../stores/gameStore'
import { sendWS, onWSMessage } from '../services/ws'
import type { ResidentData } from '../game/GameScene'

interface Message {
  role: 'user' | 'npc'
  sender: string
  text: string
}

export function ChatDrawer() {
  const { chatOpen, chatResident, openChat, closeChat, setInputFocused } = useGameStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streamingText, setStreamingText] = useState('')
  const streamingRef = useRef('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Listen for NPC interact events from Phaser
  useEffect(() => {
    return bridge.on('npc:interact', (data: unknown) => {
      const npc = data as ResidentData
      openChat({ slug: npc.slug, name: npc.name, role: npc.meta_json?.role ?? '' })
      sendWS({ type: 'start_chat', resident_slug: npc.slug })
      setMessages([])
      setStreamingText('')
      streamingRef.current = ''
    })
  }, [openChat])

  // Listen for WebSocket messages
  useEffect(() => {
    return onWSMessage((data) => {
      if (data.type === 'chat_reply') {
        if (data.done === true) {
          // Streaming complete — commit streamed text as a message
          const finalText = streamingRef.current
          if (finalText) {
            setMessages((prev) => [
              ...prev,
              { role: 'npc', sender: useGameStore.getState().chatResident?.name ?? '', text: finalText },
            ])
          }
          setStreamingText('')
          streamingRef.current = ''
        } else if (typeof data.text === 'string') {
          streamingRef.current += data.text
          setStreamingText(streamingRef.current)
        }
      }
    })
  }, [])

  const send = () => {
    const text = input.trim()
    if (!text || !chatResident) return
    setMessages((prev) => [...prev, { role: 'user', sender: '你', text }])
    sendWS({ type: 'chat_msg', text })
    setInput('')
  }

  const close = () => {
    sendWS({ type: 'end_chat' })
    closeChat()
  }

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText])

  // Escape key to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape' && chatOpen) close() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [chatOpen])

  return (
    <div style={{
      position: 'fixed', top: 48, right: 0, bottom: 0, width: 380,
      background: 'var(--bg-card)', borderLeft: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', zIndex: 20,
      transform: chatOpen ? 'translateX(0)' : 'translateX(100%)',
      transition: 'transform 0.3s ease',
    }}>
      {/* Header */}
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 40, height: 40, background: 'var(--bg-input)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>🧑‍💻</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{chatResident?.name ?? ''}</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{chatResident?.role ?? ''}</div>
        </div>
        <button onClick={close} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer', padding: '4px 8px', borderRadius: 6 }}>✕</button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            maxWidth: '85%', padding: '10px 14px', borderRadius: 12, fontSize: 13, lineHeight: 1.6,
            ...(m.role === 'user'
              ? { background: 'var(--accent-red)', color: 'white', alignSelf: 'flex-end', borderBottomRightRadius: 4 }
              : { background: 'var(--bg-input)', color: '#d4d4d8', alignSelf: 'flex-start', borderBottomLeftRadius: 4 }),
          }}>
            {m.role === 'npc' && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{m.sender}</div>}
            {m.text}
          </div>
        ))}
        {streamingText && (
          <div style={{ maxWidth: '85%', padding: '10px 14px', borderRadius: 12, fontSize: 13, lineHeight: 1.6, background: 'var(--bg-input)', color: '#d4d4d8', alignSelf: 'flex-start', borderBottomLeftRadius: 4 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{chatResident?.name ?? ''}</div>
            {streamingText}<span style={{ opacity: 0.5 }}>▌</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center' }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onFocus={() => setInputFocused(true)}
          onBlur={() => setInputFocused(false)}
          onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Enter') send() }}
          placeholder="输入消息..."
          style={{
            flex: 1, background: 'var(--bg-input)', border: '1px solid var(--border)',
            color: 'var(--text-primary)', padding: '10px 14px', borderRadius: 'var(--radius)',
            fontSize: 13, outline: 'none',
          }}
        />
        <button onClick={send} style={{
          background: 'var(--accent-red)', color: 'white', border: 'none',
          padding: '10px 16px', borderRadius: 'var(--radius)', fontSize: 13, fontWeight: 700, cursor: 'pointer',
        }}>发送</button>
        <span style={{ color: 'var(--text-muted)', fontSize: 11, whiteSpace: 'nowrap' }}>1🪙</span>
      </div>
    </div>
  )
}
