import type { ApproveInput } from '../../services/api/challenge'

export async function approveTrustedDiff(
  reviewed: boolean,
  input: ApproveInput,
  event: Pick<MouseEvent, 'isTrusted'>,
  onApprove: (
    input: ApproveInput,
    event: Pick<MouseEvent, 'isTrusted'>,
  ) => Promise<void>,
): Promise<boolean> {
  if (!reviewed || event.isTrusted !== true) return false
  await onApprove(input, event)
  return true
}
