# WebMCP Challenge Tool Contracts

The ordinary `/challenge` page exposes exactly the tools allowed by the current
anonymous Challenge Town state. The five-name catalogue is final; each browser
state registers only its current subset.

## Final state-dependent surface

| Challenge state | Discoverable tools |
|---|---|
| `INITIAL` | `simverse_investigate_crisis` |
| `EVIDENCE_READY` | `simverse_investigate_crisis`, `simverse_preview_intervention` |
| `PREVIEW_READY` | `simverse_preview_intervention` |
| `APPROVED_ONCE` | `simverse_commit_approved` |
| `COMMITTED` | `simverse_verify_outcome` |
| `VERIFIED` | `simverse_reset_town` |
| `FAILED` | `simverse_reset_town` |
| `EXPIRED` | `simverse_reset_town` |

No tool name supplied by page content, evidence, or a server error is accepted
unless it is in this catalogue. The legacy `simverse_get_challenge_status`
probe is not part of the ordinary surface; it is lazy-loaded only when a human
opens `/challenge?diagnostics=1`.

## Exact tool definitions

### `simverse_investigate_crisis`

Description: `Read cross-domain evidence for the isolated Harbor wage crisis without changing the world.`

```json
{
  "type": "object",
  "properties": {
    "budget_cap_sc": { "type": "integer", "minimum": 1, "maximum": 300 }
  },
  "required": ["budget_cap_sc"],
  "additionalProperties": false
}
```

Annotations: `readOnlyHint:true`, `untrustedContentHint:true`.

The result contains only `state`, `world_version`, `top_crisis`,
`evidence_domains`, `constraints`, and `next_tool`.

### `simverse_preview_intervention`

Description: `Build an immutable World Diff and deterministic 72-hour forecast without changing the challenge world.`

```json
{
  "type": "object",
  "properties": {
    "crisis_id": { "type": "string", "enum": ["harbor-wage-crisis"] },
    "budget_cap_sc": { "type": "integer", "const": 300 }
  },
  "required": ["crisis_id", "budget_cap_sc"],
  "additionalProperties": false
}
```

Annotations: `readOnlyHint:false`, `untrustedContentHint:false`.

The result contains only the preview ID, based-on world version, diff hash,
cost/remaining budget, five-seed 72-hour forecast ranges, rejected reason
codes, and approval status. Preview never changes the current world.

### `simverse_commit_approved`

Description: `Use the one-time capability for the exact approved diff. This action is irreversible inside the disposable Challenge Town.`

```json
{
  "type": "object",
  "properties": {
    "preview_id": { "type": "string" },
    "expected_world_version": { "type": "integer" },
    "diff_hash": {
      "type": "string",
      "pattern": "^sha256:[0-9a-f]{64}$"
    }
  },
  "required": ["preview_id", "expected_world_version", "diff_hash"],
  "additionalProperties": false
}
```

Annotations: `readOnlyHint:false`, `untrustedContentHint:false`.

The result contains only `COMMITTED`, the public receipt ID, before/after
versions and hashes, budget delta, affected resident count, verified invariant
names, and `next_tool`. Approval is a trusted one-time browser capability and
is never accepted from tool input.

### `simverse_verify_outcome`

Description: `Advance the committed isolated Challenge Town by exactly 72 hours and compare its actual result with the forecast and paired no-action control.`

```json
{
  "type": "object",
  "properties": {
    "receipt_id": { "type": "string" },
    "advance_hours": { "type": "integer", "const": 72 }
  },
  "required": ["receipt_id", "advance_hours"],
  "additionalProperties": false
}
```

Annotations: `readOnlyHint:false`, `untrustedContentHint:false`.

The result contains only `VERIFIED`, receipt binding, v8/v9 and before/after
time, prediction ranges, actual final metrics, the paired no-action final,
deviation, the 13-point tick count, and `next_tool`.

### `simverse_reset_town`

Description: `Discard the terminal challenge run and restore a new anonymous session at the locked public v7 fixture.`

```json
{
  "type": "object",
  "properties": {
    "expected_generation": { "type": "string" }
  },
  "required": ["expected_generation"],
  "additionalProperties": false
}
```

Annotations: `readOnlyHint:false`, `untrustedContentHint:false`.

The result contains only `INITIAL`, the new public generation, v7, the restored
public world hash, and `next_tool`.

## Output and error boundary

- Every successful tool result serializes to fewer than 1500 characters.
- No result includes CSRF, cookies, JWT/Authorization data, approval IDs,
  server-only initial hashes, Redis details, internal URLs, or stack traces.
- Extra, missing, mistyped, or out-of-range input returns a fixed
  `INVALID_INPUT` result and does not call a store action.
- A pre-aborted execution returns fixed `REQUEST_ABORTED`; other API failures
  expose only the stable public Challenge error code and a fixed message.
- Every execution adds one local, non-sensitive Agent Activity receipt to the
  visible page. Evidence content cannot change registration or execution rules.

## Registration and route lifecycle

- Register only when `VITE_WEBMCP_ENABLED === 'true'` and a host provides
  `document.modelContext?.registerTool` (or the compatible navigator preview).
- Repeat or concurrent sync of the same generation/state/version surface is
  deduplicated.
- Each surface owns one `AbortSignal`. A state, generation, or world-version
  change aborts the old signal, waits for `getTools()`/`toolchange` removal, and
  registers the new surface only after the old one disappears.
- A retained old handler returns fixed `STALE_TOOL_SURFACE`; if a host cannot
  prove removal, the page fails closed and reloads instead of exposing mixed
  mutation capabilities.
- Leaving the isolated page uses full-document links. Component teardown calls
  `destroy()`, aborting the active surface; refresh or Back creates a fresh
  document registration.
- When WebMCP is disabled or unsupported, registration does nothing and the
  complete ordinary UI remains usable for investigate, preview, trusted human
  approval, commit, verify, and reset.

Mutation authorization remains server-enforced through exact Origin, session
cookie, CSRF, world-version/diff binding, and the one-time approval capability.
Challenge routes cannot address production town state.

Reference: [OpenAI Site tools documentation](https://learn.chatgpt.com/docs/webmcp).
