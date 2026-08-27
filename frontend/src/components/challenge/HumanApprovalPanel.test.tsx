import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type {
  ApproveInput,
  ChallengeProjection,
} from '../../services/api/challenge'
import { HumanApprovalPanel } from './HumanApprovalPanel'
import { approveTrustedDiff } from './humanApprovalGate'

afterEach(cleanup)

function approvalSession(
  overrides: Partial<ChallengeProjection> = {},
): ChallengeProjection {
  const residentIds = Array.from(
    { length: 6 },
    (_, index) => `harbor-resident-${String(index + 1).padStart(2, '0')}`,
  )
  return {
    session_generation: 'generation-visible-not-secret',
    state: 'PREVIEW_READY',
    scenario_id: 'harbor-wage-crisis-v1',
    fixture_version: 1,
    world_version: 7,
    world_hash: `sha256:${'a'.repeat(64)}`,
    world_time: '2042-06-12T08:00:00Z',
    budget_sc: 300,
    tool_surface: ['simverse_preview_intervention'],
    expires_at: '2042-06-12T08:15:00Z',
    csrf_token: 'csrf-server-only-secret',
    world: {
      scenario_id: 'harbor-wage-crisis-v1',
      fixture_version: 1,
      world_version: 7,
      world_time: '2042-06-12T08:00:00Z',
      budget_sc: 300,
      harbor_open: true,
      residents: residentIds.map((resident_id, index) => ({
        resident_id,
        name: `Resident ${index + 1}`,
        cash_sc: 10,
        unpaid_wage_sc: 30,
        food_risk: index < 2 ? 'HIGH' : 'MEDIUM',
        food_credit_sc: 0,
        stabilized: false,
      })),
      employers: [
        {
          employer_id: 'harbor-employer-a',
          name: 'Employer A',
          overdue_payroll_sc: 90,
          repayment_claim_sc: 0,
          escrow_status: 'NONE',
        },
        {
          employer_id: 'harbor-employer-b',
          name: 'Employer B',
          overdue_payroll_sc: 90,
          repayment_claim_sc: 0,
          escrow_status: 'NONE',
        },
      ],
      relationships: [],
      events: [],
      metrics: {
        unpaid_residents: 6,
        high_food_risk_residents: 2,
        social_tension: 68,
        strike_risk_pct: 74,
        stabilized_residents: 0,
      },
    },
    evidence: null,
    preview: {
      preview_id: 'preview-visible-01',
      crisis_id: 'harbor-wage-crisis',
      based_on_world_version: 7,
      intervention_id: 'harbor-wage-bridge',
      total_cost_sc: 240,
      remaining_budget_sc: 60,
      diff: {
        scenario_id: 'harbor-wage-crisis-v1',
        session_generation: 'generation-visible-not-secret',
        preview_id: 'preview-visible-01',
        based_on_world_version: 7,
        budget_before_sc: 300,
        budget_after_sc: 60,
        resident_cash_changes: residentIds.map((resident_id) => ({
          resident_id,
          before_sc: 10,
          delta_sc: 30,
          after_sc: 40,
        })),
        food_credit_changes: residentIds.slice(0, 2).map((resident_id) => ({
          resident_id,
          before_sc: 0,
          delta_sc: 20,
          after_sc: 20,
        })),
        employer_claims_created: [
          { employer_id: 'harbor-employer-a', amount_sc: 90, status: 'PENDING' },
          { employer_id: 'harbor-employer-b', amount_sc: 90, status: 'PENDING' },
        ],
        events_created: [{
          event_id: 'employer-escrow-mediation',
          event_type: 'MEDIATION',
          region_id: 'harbor-district',
          title: 'Employer escrow mediation opened',
          description: 'Harbor employers enter mediation.',
          occurs_at: '2042-06-12T08:05:00Z',
        }],
        explicitly_unchanged: [
          'resident_personality',
          'resident_preferences',
          'resident_intentions',
          'direct_relationship_scores',
          'harbor_operating_status',
          'production_town_state',
        ],
      },
      diff_hash: `sha256:${'b'.repeat(64)}`,
      forecast: {
        seeds: [101, 102, 103, 104, 105],
        high_food_risk_residents: { min: 0, max: 1 },
        social_tension: { min: 50, max: 58 },
        strike_risk_pct: { min: 28, max: 42 },
        stabilized_residents: { min: 5, max: 6 },
      },
      rejected_alternatives: [],
      created_at: '2042-06-12T08:05:00Z',
    },
    approval_fingerprint: null,
    approval_expires_at: null,
    receipt: null,
    verification: null,
    ...overrides,
  }
}

describe('HumanApprovalPanel', () => {
  it('shows the complete immutable diff and keeps programmatic approval disabled', () => {
    const onApprove = vi.fn().mockResolvedValue(undefined)
    const { container } = render(
      <HumanApprovalPanel
        session={approvalSession()}
        onApprove={onApprove}
        onRevoke={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText('Commit capability is not available to the agent.')).toBeInTheDocument()
    expect(screen.getByText('Review this exact diff to create a one-time approval.')).toBeInTheDocument()
    expect(screen.getAllByTestId('approval-resident-change')).toHaveLength(6)
    expect(screen.getAllByTestId('approval-food-change')).toHaveLength(2)
    expect(screen.getAllByTestId('approval-employer-claim')).toHaveLength(2)
    expect(screen.getByText('employer-escrow-mediation')).toBeInTheDocument()
    expect(screen.getByText('Budget 300 SC → 60 SC')).toBeInTheDocument()
    expect(screen.getAllByTestId('approval-unchanged')).toHaveLength(6)

    const approve = screen.getByRole('button', { name: 'Create one-time approval' })
    expect(approve).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', {
      name: 'I reviewed this exact World Diff.',
    }))
    expect(approve).toBeEnabled()
    approve.click()
    expect(onApprove).not.toHaveBeenCalled()
    expect(container.innerHTML).not.toContain('csrf-server-only-secret')
    expect(container.innerHTML).not.toContain('sv_challenge_approval')
    expect(container.innerHTML).not.toContain('approval-server-only-secret')
  })

  it('dispatches one exact approval only for a trusted reviewed event', async () => {
    const input: ApproveInput = {
      preview_id: 'preview-visible-01',
      expected_world_version: 7,
      diff_hash: `sha256:${'b'.repeat(64)}`,
    }
    const onApprove = vi.fn().mockResolvedValue(undefined)

    expect(await approveTrustedDiff(false, input, { isTrusted: true }, onApprove)).toBe(false)
    expect(await approveTrustedDiff(true, input, { isTrusted: false }, onApprove)).toBe(false)
    expect(await approveTrustedDiff(true, input, { isTrusted: true }, onApprove)).toBe(true)

    expect(onApprove).toHaveBeenCalledTimes(1)
    expect(onApprove).toHaveBeenCalledWith(input, { isTrusted: true })
  })

  it('shows only the safe approval fingerprint and removes it after revoke projection', () => {
    const onRevoke = vi.fn().mockResolvedValue(undefined)
    const { container, rerender } = render(
      <HumanApprovalPanel
        session={approvalSession({
          state: 'APPROVED_ONCE',
          tool_surface: ['simverse_commit_approved'],
          approval_fingerprint: 'appr-A1B2',
          approval_expires_at: '2042-06-12T08:06:30Z',
        })}
        onApprove={vi.fn().mockResolvedValue(undefined)}
        onRevoke={onRevoke}
      />,
    )

    expect(screen.getByText('Approved once')).toBeInTheDocument()
    expect(screen.getByText('appr-A1B2')).toBeInTheDocument()
    expect(screen.getByText('World v7')).toBeInTheDocument()
    expect(screen.getByText('sha256:bbbbbbbbbbbb…')).toBeInTheDocument()
    expect(screen.getByText('2042-06-12T08:06:30Z')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Revoke approval' }))
    expect(onRevoke).toHaveBeenCalledTimes(1)

    rerender(
      <HumanApprovalPanel
        session={approvalSession()}
        onApprove={vi.fn().mockResolvedValue(undefined)}
        onRevoke={onRevoke}
      />,
    )
    expect(screen.queryByText('appr-A1B2')).not.toBeInTheDocument()
    expect(container.innerHTML).not.toContain('csrf-server-only-secret')
    expect(container.innerHTML).not.toContain('approval-server-only-secret')
  })
})
