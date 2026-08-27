import type {
  ChallengeWorld,
  EvidenceSnapshot,
} from '../../services/api/challenge'

interface LivingWorldPanelProps {
  world: ChallengeWorld
  evidence: EvidenceSnapshot | null
}

const RESIDENT_POSITIONS = [
  [94, 88],
  [126, 120],
  [166, 78],
  [214, 112],
  [254, 72],
  [288, 116],
] as const

export function LivingWorldPanel({ world, evidence }: LivingWorldPanelProps) {
  const affected = new Set(evidence?.affected_resident_ids ?? [])
  const focused = evidence?.region_id === 'harbor'
  const metrics = world.metrics

  return (
    <section className="challenge-living-world" aria-labelledby="living-world-title">
      <header>
        <div>
          <p>CHALLENGE-LOCAL WORLD VIEW</p>
          <h2 id="living-world-title">Harbor district</h2>
        </div>
        <div className="challenge-world-counts">
          {evidence ? (
            <span data-testid="evidence-world-version">
              Evidence v{evidence.based_on_world_version}
            </span>
          ) : null}
          <span>{world.residents.length} residents</span>
          <span>{world.employers.length} employers</span>
          <time dateTime={world.world_time}>{world.world_time}</time>
        </div>
      </header>

      <div className="challenge-harbor-layout">
        <svg
          className="challenge-harbor-map"
          data-focused={focused ? 'true' : 'false'}
          data-testid="harbor-map"
          role="img"
          aria-label="Harbor district challenge map"
          viewBox="0 0 420 220"
        >
          <defs>
            <linearGradient id="harbor-water" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#10324a" />
              <stop offset="1" stopColor="#071923" />
            </linearGradient>
            <filter id="harbor-glow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          <rect width="420" height="220" rx="18" fill="url(#harbor-water)" />
          <path className="challenge-shore" d="M0 22h310l36 28-18 35 47 37-18 98H0Z" />
          <path className="challenge-road" d="M24 47h270M44 151h274M70 42v119M190 42v119" />
          <path className="challenge-pier" d="M302 61h96v18h-96M326 112h72v18h-72M294 161h104v18H294" />
          <g className="challenge-employers" aria-label="Harbor employers">
            <rect x="38" y="55" width="44" height="30" rx="5" />
            <rect x="194" y="119" width="48" height="32" rx="5" />
          </g>
          {world.residents.map((resident, index) => {
            const [cx, cy] = RESIDENT_POSITIONS[index] ?? [320, 90]
            const isAffected = affected.has(resident.resident_id)
            return (
              <g
                className="challenge-resident-marker"
                data-affected={isAffected ? 'true' : 'false'}
                data-testid={isAffected ? 'affected-resident' : undefined}
                key={resident.resident_id}
                transform={`translate(${cx} ${cy})`}
              >
                <circle r="9" />
                <circle className="challenge-resident-core" r="3" />
                <title>{resident.name}</title>
              </g>
            )
          })}
          <text x="302" y="204">HARBOR</text>
        </svg>

        <aside className="challenge-harbor-focus" data-focused={focused ? 'true' : 'false'}>
          <i />
          <div>
            <strong>{focused ? 'Harbor focus active' : 'Harbor crisis awaiting evidence'}</strong>
            <span>
              {focused
                ? `${affected.size} affected residents highlighted from evidence.`
                : 'Investigate to bind evidence to the isolated fixture.'}
            </span>
          </div>
        </aside>
      </div>

      <div className="challenge-metrics" aria-label="Challenge world metrics">
        <article data-testid="metric-unpaid"><span>Unpaid residents</span><strong>{metrics.unpaid_residents}</strong></article>
        <article data-testid="metric-high-risk"><span>High food risk</span><strong>{metrics.high_food_risk_residents}</strong></article>
        <article data-testid="metric-tension"><span>Social tension</span><strong>{metrics.social_tension}</strong></article>
        <article data-testid="metric-strike"><span>Strike risk</span><strong>{metrics.strike_risk_pct}%</strong></article>
        <article data-testid="metric-stabilized"><span>Stabilized</span><strong>{metrics.stabilized_residents}</strong></article>
      </div>
    </section>
  )
}
