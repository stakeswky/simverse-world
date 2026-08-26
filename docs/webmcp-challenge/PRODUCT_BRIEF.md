# Simverse Civic Copilot — Product Brief

## One sentence

Co-govern a living AI town with an agent that can surface evidence, preview interventions, and enact only the changes you approve.

## Problem

Simverse is a continuously running society. A single civic problem can be distributed across the map, resident relationships, economic records, and event history. A human can investigate it manually, but doing so requires context switching and makes it easy to overlook evidence or act on the wrong resident, district, or budget.

## Product thesis

WebMCP should be the product's collaboration layer, not a thin API wrapper. A person and an agent share the same live page and, where authentication is required, the page's existing signed-in session:

- The agent interprets a complex world and structures evidence.
- The page shows exactly what the agent found and what it proposes.
- The human makes value judgments and retains final authority.
- The world visibly changes only after an explicit approval step.

## Hero scenario

The planned resettable Challenge Town begins on Day 7. The harbor district has unpaid wages, worsening resident sentiment, and tension between two groups. The evidence is intentionally split across economic, relationship, map, and event data.

The intended flow is:

1. **Diagnose** — surface the highest-risk town signals.
2. **Focus** — move the shared page to the harbor evidence.
3. **Draft** — produce three bounded interventions.
4. **Preview** — show cost, affected residents, expected benefit, risk, and uncertainty.
5. **Stage** — render a pending world-state diff.
6. **Approve and commit** — require explicit human authorization before mutation.
7. **Verify** — return a receipt and show the resulting economic, relationship, and map changes.
8. **Reset** — restore the deterministic challenge scenario.

## Day-0 scope

Day 0 is intended to prove the riskiest integration before building the full workflow:

```text
ChatGPT in-app browser
  → opens /challenge
  → discovers simverse_get_challenge_status
  → calls it
  → receives a stable result
  → page records the call visibly
```

The source-level probe is fixed-data and read-only. The returned `resettable:true` declares the seeded fixture's intended contract; Day 0 does not yet implement a reset handler or provision a backend town instance. The probe deliberately avoids backend, LLM, authentication, and production-world dependencies so browser discovery and deployment failures can be diagnosed independently. Discovery remains unverified until the exact build passes the public browser matrix.

## Users

- Simulation-game designers investigating emergent behavior.
- Educators using a living society to discuss policy tradeoffs.
- World administrators who need a safe, auditable control surface.
- People who find dense maps and dashboards difficult to navigate manually.

## Success measures

Primary benchmark task:

> Find the town's most urgent problem and prepare a safe intervention costing no more than 300 SC.

Compare the ordinary UI with the WebMCP flow across five repeated trials:

- Completion time.
- Page changes.
- Clicks.
- Wrong resident or district selections.
- Successful completion rate.
- Whether a mutation occurred without a correct preview and approval.

## Non-goals for the Challenge sprint

- Reworking NPC intelligence, schedules, or economic rules.
- Exposing a broad CRUD surface.
- Letting an agent bypass the visible page, user permissions, or approval.
- Requiring judges to register, supply an API key, or configure an external model.
- Using live LLM generation on the critical demo path.
