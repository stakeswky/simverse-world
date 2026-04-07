import type { ForgeStatusResponse } from '../../services/api'

interface ForgePreviewProps {
  state: ForgeStatusResponse | null
}

// Stub — full implementation in Task 6
export function ForgePreview({ state: _ }: ForgePreviewProps) {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', padding: 24 }}>
      实时预览（Task 6 实现）
    </div>
  )
}
