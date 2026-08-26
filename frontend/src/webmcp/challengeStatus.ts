export interface ChallengeStatus {
  readonly town: 'WebMCP Challenge Town'
  readonly world_time: 'Day 7, 09:30'
  readonly scenario: 'Harbor district tension'
  readonly tool_version: '0.1.0'
  readonly resettable: true
}

const CHALLENGE_STATUS: ChallengeStatus = Object.freeze({
  town: 'WebMCP Challenge Town',
  world_time: 'Day 7, 09:30',
  scenario: 'Harbor district tension',
  tool_version: '0.1.0',
  resettable: true,
})

export function getChallengeStatus(): ChallengeStatus {
  return { ...CHALLENGE_STATUS }
}
