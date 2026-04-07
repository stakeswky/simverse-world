import type { ForgeStatusResponse } from '../../services/api'

interface ForgeChatProps {
  onStateUpdate: (state: ForgeStatusResponse) => void
  onComplete: (residentId: string) => void
}

// Stub — full implementation in Task 5
export function ForgeChat({ onStateUpdate: _, onComplete: __ }: ForgeChatProps) {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
      炼化对话面板（Task 5 实现）
    </div>
  )
}
