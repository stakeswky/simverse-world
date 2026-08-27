# Three-Minute Civic Copilot Demo

Total duration: 2:55

Record the actual public Challenge page and ChatGPT in-app browser in one readable composition. The task shown on screen and sent to the agent is:

> Find the town's most urgent problem and create a safe intervention under 300 SC. Do not close the harbor or rewrite resident preferences.

| Time | Visual and Site Tool action | Narration |
|---|---|---|
| 0:00–0:15 | Living Simverse town, then `/challenge` beside ChatGPT | “A persistent AI society spreads one civic problem across people, places, relationships, and money. Civic Copilot turns that complexity into one shared, inspectable workspace.” |
| 0:15–0:38 | Call `simverse_investigate_crisis`; Harbor evidence appears in the page | “The agent uses a purpose-built Site Tool to find the Harbor wage crisis. Its conclusion is grounded in the same evidence I can see.” |
| 0:38–1:05 | Call `simverse_preview_intervention`; show the immutable diff, 240 SC cost, warnings, rejected alternatives, and Prediction range | “It proposes a bounded relief-and-mediation package. Preview changes nothing: it shows the exact diff, rejects unsafe alternatives, and forecasts five deterministic futures under my 300 SC limit.” |
| 1:05–1:30 | Show that commit is absent; tick the visible approval checkbox and press the ordinary approval button; the commit tool appears | “The agent cannot approve its own proposal. Only this visible ceremony creates a short-lived, one-time capability for this exact version and diff.” |
| 1:30–1:52 | Call `simverse_commit_approved`; show receipt, v7 to v8, and remaining 60 SC | “Commit consumes that capability once. A replay, stale version, changed hash, or cross-session request is rejected by the server.” |
| 1:52–2:25 | Call `simverse_verify_outcome`; show the 72-hour chart and labels Prediction, Actual, No-action control | “After 72 hours, Actual lands inside the Prediction range: high food risk falls to one, tension to 54, and five residents stabilize. The paired No-action control reaches a strike.” |
| 2:25–2:43 | Call `simverse_reset_town`; show a new generation at v7 and the locked initial hash | “Reset discards the terminal run and proves reproducibility: a fresh anonymous town returns to the locked fixture.” |
| 2:43–2:55 | Agent Activity receipts, ordinary UI fallback, product lockup | “WebMCP makes Simverse a human-agent civic workspace, while the person keeps final authority and the ordinary page remains complete.” |

## Required captures

- The public URL, ChatGPT conversation, selected model, and discoverable Site Tool list.
- Each tool invocation when it changes the visible page or available catalogue.
- Harbor cross-domain evidence and the exact 300 SC constraint.
- Preview diff, Prediction range, 240 SC cost, warnings, and rejected alternatives.
- The visible approval checkbox/button and proof that commit was absent before approval.
- Commit receipt with v7 to v8 and the 60 SC remainder.
- Verification labels Prediction, Actual, and No-action control with the v9 receipt binding.
- Reset to a new generation, v7, and the locked initial public hash.
- Agent Activity receipts and the complete ordinary-UI fallback.

## Recording rules

- Use English UI, narration, and captions; Chinese subtitles are optional.
- Keep tool names, exact numbers, receipt/version fields, and the approval control legible.
- Use the locked deterministic fixture and the exact deployed commit; do not splice local evidence into a public-host claim.
- Show no tokens, cookies, account email, approval identifiers, private resident data, DevTools secrets, or admin configuration.
- The diagnostics-only status probe is Day-0 compatibility evidence, not part of this hero demo.
