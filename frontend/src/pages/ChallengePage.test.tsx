import '@testing-library/jest-dom/vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChallengePage } from './ChallengePage'
import { getChallengeStatus } from '../webmcp/challengeStatus'
import { resetAgentActivityForTests } from '../webmcp/activity'
import { resetWebMcpRegistrationsForTests } from '../webmcp/registerChallengeStatusTool'
import type { WebMcpToolDefinition } from '../webmcp/types'

afterEach(() => {
  cleanup()
  resetWebMcpRegistrationsForTests()
  resetAgentActivityForTests()
  vi.unstubAllEnvs()
  Reflect.deleteProperty(document, 'modelContext')
  Reflect.deleteProperty(navigator, 'modelContext')
})

describe('ChallengePage', () => {
  it('shows a visible activity receipt after the agent calls the Site Tool', async () => {
    vi.stubEnv('VITE_WEBMCP_ENABLED', 'true')
    let registeredTool: WebMcpToolDefinition | undefined
    const registerTool = vi.fn((tool: WebMcpToolDefinition) => {
      registeredTool = tool
    })
    Object.defineProperty(document, 'modelContext', {
      configurable: true,
      value: { registerTool },
    })

    render(<StrictMode><MemoryRouter><ChallengePage /></MemoryRouter></StrictMode>)

    expect(screen.getByRole('heading', { name: 'Co-govern a living AI town.' })).toBeInTheDocument()
    expect(screen.getByText('0.1.0')).toBeInTheDocument()
    expect(screen.getByText('Waiting for a Site Tool call')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Site Tool ready')).toBeInTheDocument())
    expect(registerTool).toHaveBeenCalledTimes(1)

    let result: unknown
    await act(async () => {
      result = await registeredTool?.execute({})
    })

    expect(result).toEqual(getChallengeStatus())
    expect(screen.getByText('simverse_get_challenge_status')).toBeInTheDocument()
    expect(screen.getByText(/Completed in \d+ ms/)).toBeInTheDocument()
    expect(screen.queryByText('Waiting for a Site Tool call')).not.toBeInTheDocument()
  })

  it('keeps the normal page usable when Site Tools are unsupported', async () => {
    vi.stubEnv('VITE_WEBMCP_ENABLED', 'true')

    render(<MemoryRouter><ChallengePage /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByText('Site Tools unavailable in this browser')).toBeInTheDocument()
    })
    expect(screen.getByText('WebMCP Challenge Town')).toBeInTheDocument()
    expect(screen.getByText('Harbor district tension')).toBeInTheDocument()
  })

  it('registers through Chrome 149 navigator.modelContext', async () => {
    vi.stubEnv('VITE_WEBMCP_ENABLED', 'true')
    const registerTool = vi.fn()
    Object.defineProperty(navigator, 'modelContext', {
      configurable: true,
      value: { registerTool },
    })

    render(<MemoryRouter><ChallengePage /></MemoryRouter>)

    await waitFor(() => expect(screen.getByText('Site Tool ready')).toBeInTheDocument())
    expect(registerTool).toHaveBeenCalledTimes(1)
  })

  it('uses full-document links when leaving the challenge surface', () => {
    render(<MemoryRouter><ChallengePage /></MemoryRouter>)

    expect(screen.getByRole('link', { name: 'Live town' })).toHaveAttribute('href', '/town')
    expect(screen.getByRole('link', { name: 'Enter world' })).toHaveAttribute('href', '/login')
  })
})
