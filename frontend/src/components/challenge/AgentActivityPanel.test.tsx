import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import {
  publishAgentActivity,
  resetAgentActivityForTests,
} from '../../webmcp/activity'
import { AgentActivityPanel } from './AgentActivityPanel'

afterEach(() => {
  cleanup()
  resetAgentActivityForTests()
})

describe('AgentActivityPanel', () => {
  it('renders an empty visible receipt boundary', () => {
    render(<AgentActivityPanel toolDocument={document} />)

    expect(screen.getByRole('region', { name: 'Agent Activity' })).toBeInTheDocument()
    expect(screen.getByText('No tool calls yet')).toBeInTheDocument()
  })

  it('renders safe phase, outcome, duration, reason, world, and hash fields', () => {
    publishAgentActivity(document, {
      toolName: 'simverse_investigate_crisis',
      phase: 'investigate',
      outcome: 'completed',
      durationMs: 4,
      reasonCode: 'EVIDENCE_READY',
      worldVersionBefore: 7,
      worldVersionAfter: 7,
      receiptId: null,
      fingerprint: 'sha256:aaaaaaaaaaaa',
    })

    render(<AgentActivityPanel toolDocument={document} />)

    expect(screen.getByText('simverse_investigate_crisis')).toBeInTheDocument()
    expect(screen.getByText('investigate · completed')).toBeInTheDocument()
    expect(screen.getByText('4 ms')).toBeInTheDocument()
    expect(screen.getByText('EVIDENCE_READY')).toBeInTheDocument()
    expect(screen.getByText('World v7 → v7')).toBeInTheDocument()
    expect(screen.getByText('sha256:aaaaaaaaaaaa')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/csrf|cookie|approvalId|Bearer/i)
  })
})
