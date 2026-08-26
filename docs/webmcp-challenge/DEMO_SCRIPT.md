# Three-Minute Demo Script

Target runtime: `2:55`. The final video must be public, under three minutes, and include spoken audio. Record the actual ChatGPT in-app browser, Site Tool calls, Simverse page changes, and final receipt in one legible frame.

| Time | Visual | Narration |
|---|---|---|
| 0:00–0:15 | A running Simverse town; fast cuts across map, relationships, economy, and events | “A living AI society is difficult to understand and even harder to govern safely. Its problems are spread across people, places, relationships, and money.” |
| 0:15–0:30 | Open `/challenge` beside the ChatGPT conversation | “Simverse Civic Copilot gives a person and an agent the same live page. The agent investigates complexity; the person keeps final authority.” |
| 0:30–0:55 | Agent calls `inspect_town_signals`; harbor risk glows on the map | “The agent discovers purpose-built Site Tools and identifies a harbor wage crisis without guessing through the interface.” |
| 0:55–1:20 | `focus_evidence` opens residents, wage records, relationship tension, and timeline | “Every conclusion is grounded in evidence that appears on the page for me to inspect.” |
| 1:20–1:50 | `draft_interventions` produces three bounded plan cards | “The agent drafts alternatives instead of silently choosing policy: emergency aid, mediation, or a public commission.” |
| 1:50–2:15 | `preview_intervention` shows cost, affected residents, benefit, risk, and uncertainty | “Before anything changes, Simverse previews the exact impact and checks my 300 Soul Coin limit.” |
| 2:15–2:35 | A staged world diff appears; user explicitly approves; `commit_intervention` runs | “The change remains uncommitted until I approve this exact diff. The agent cannot expand the action after approval.” |
| 2:35–2:50 | `verify_outcome` shows receipt and before/after economy and relationship values | “The world changes visibly, and the agent verifies the result with a receipt tied to the new world revision.” |
| 2:50–2:55 | Product lockup and one-line architecture | “WebMCP turns Simverse into a shared civic workspace for humans and agents—not an invisible API.” |

## Required captures

- ChatGPT conversation and selected model.
- Available Site Tools list.
- Each tool invocation at the moment it changes the page.
- Agent Activity trace.
- Evidence focus on the harbor district.
- Three intervention cards.
- Preview and staged diff before approval.
- The user's explicit approval action.
- Commit receipt and before/after verification.
- Reset back to the initial deterministic state.

## Recording rules

- Use English UI, narration, and captions; optionally add Chinese subtitles.
- Keep the browser zoom high enough to read tool names and results.
- Use seeded data and a deterministic path; do not depend on a live external LLM for the critical flow.
- Do not use unlicensed music, footage, trademarks, or assets.
- Show no tokens, account email, DevTools secrets, admin configuration, or private resident data.
- The Day-0 status probe is a technical proof, not the final hero demo. Replace it with the complete flow only after every stage is live and tested.
