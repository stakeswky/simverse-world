# WebMCP Tool Contracts

The tool surface follows the state of the shared `/challenge` page. Only tools valid for the current stage should be discoverable. The Day-0 implementation registers one read-only probe; the remaining contracts are the planned hero flow and are not yet claimed as implemented.

## Implemented on Day 0

### `simverse_get_challenge_status`

Purpose: verify end-to-end Site Tool discovery, execution, stable output, and visible page feedback without reading credentials or mutating a world.

Contract excerpt (the implementation also performs runtime input validation, fixed-error handling, registration deduplication, and Activity receipt recording):

```ts
document.modelContext.registerTool({
  name: 'simverse_get_challenge_status',
  description: 'Read the fixed Day-0 status for the Simverse WebMCP Challenge Town. This tool does not change the world.',
  inputSchema: {
    type: 'object',
    properties: {},
    additionalProperties: false,
  },
  annotations: { readOnlyHint: true },
  execute: async () => ({
    town: 'WebMCP Challenge Town',
    world_time: 'Day 7, 09:30',
    scenario: 'Harbor district tension',
    tool_version: '0.1.0',
    resettable: true,
  }),
})
```

Success result:

```json
{
  "town": "WebMCP Challenge Town",
  "world_time": "Day 7, 09:30",
  "scenario": "Harbor district tension",
  "tool_version": "0.1.0",
  "resettable": true
}
```

Side effects: no world-state effect. A local, non-sensitive Agent Activity receipt is appended to the open page so a person can verify that the tool ran.

`resettable:true` is part of the planned seeded-fixture contract. It does not claim that Day 0 already implements `reset_challenge_town` or provisions an isolated backend instance.

Failure behavior: return a fixed error code and message. Never serialize the original error, input, authorization data, request headers, or stack.

## Planned state-dependent surface

| Page state | Discoverable tools | Effect |
|---|---|---|
| Initial | `inspect_town_signals`, `focus_evidence`, `draft_interventions` | Read and focus shared evidence |
| Draft exists | `preview_intervention`, `discard_intervention` | Calculate impact or discard a draft |
| Preview accepted | `stage_intervention` | Create an uncommitted, visible world diff |
| Explicit human approval | `commit_intervention` | Apply the exact staged diff |
| Committed | `verify_outcome`, `reset_challenge_town` | Read a receipt or reset the isolated town |

Mutation tools will use narrow identifiers and revision tokens. A commit must fail closed if the scenario revision, preview hash, approval record, or authenticated permission no longer matches.

## Registration rules

- Register only when `VITE_WEBMCP_ENABLED === 'true'`.
- Feature-detect `document.modelContext?.registerTool`.
- Deduplicate concurrent and React Strict Mode registration per `Document`.
- Permit a new registration for a new `Document` after refresh.
- Keep normal browser UI functional when WebMCP is unavailable.
- Use document-navigation links on the Day-0 page so leaving `/challenge` creates a fresh page rather than carrying its tool into another Simverse SPA route.
- Do not invent an unregister API. The current OpenAI guide demonstrates `registerTool` but does not document a removal contract; browser back/forward and programmatic SPA route-change lifecycle remain live-test blockers before dynamic mutation tools ship.
- In anonymous Judge Mode, bind mutations to a short-lived server-side Challenge session that cannot address production. In signed-in product use, reuse existing application authorization. Both modes keep validation and final approval server-enforced.

Reference: [OpenAI Site tools documentation](https://learn.chatgpt.com/docs/webmcp).
