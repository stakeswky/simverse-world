# Challenge Security Boundary

The Challenge experience must demonstrate useful agent control without giving an agent invisible or broader authority than the person using the page.

## Day-0 boundary

The implemented status probe is intentionally low risk:

- `/challenge` requires no account or judge credentials.
- The tool returns a fixed five-field object already visible on the page.
- The tool does not call the Simverse API, an LLM, `localStorage`, `sessionStorage`, cookies, URL parameters, or Zustand authentication state.
- It does not read JWTs, `Authorization` headers, request headers, internal exceptions, or server state.
- It does not change the production town, database, economy, residents, relationships, or Agent Player records.
- Activity history stores only tool name, outcome, duration, timestamp, and a generated local ID.
- Registration errors become a fixed public state; execution errors become fixed public responses. Raw errors and stacks are never logged or returned.

## Threats and controls

| Threat | Control |
|---|---|
| Unsupported browser breaks the app | Feature detection and a normal-browser fallback |
| Duplicate Strict Mode registration | One in-flight registration promise per `Document` |
| Malformed or oversized input | Empty object schema, `additionalProperties:false`, and runtime empty-input validation |
| Credential leakage in errors | `catch {}` without binding or serializing the original exception |
| Tool result drifts from visible UI | Page and tool read the same immutable status source |
| Agent claims a call occurred when it did not | Activity receipt is written by the execute handler to a module-private store, not a forgeable DOM event |
| Challenge work mutates production data | Day-0 has no backend call; later flows use a separate ephemeral town |

## Mutation requirements for later phases

No state-changing tool may be released until it has all of the following:

1. A plain-language side-effect description.
2. A narrow authorization boundary: an ephemeral server-bound Challenge session in anonymous Judge Mode, or existing user authentication and authorization in the signed-in product.
3. A dedicated Challenge Town identifier that cannot resolve to production.
4. Server-side schema validation and allowlisted operation types.
5. A dry-run preview containing cost, affected entities, uncertainty, and warnings.
6. A visible staged diff and an explicit human approval record.
7. A short-lived preview hash and world revision checked again at commit time.
8. Idempotency and replay protection.
9. An immutable execution receipt with before/after revisions.
10. A deterministic reset path and abuse rate limits.

## Data displayed to judges

Only seeded fictional Challenge Town data may appear. Do not expose private chats, memories, hidden resident goals, personal account data, balances tied to real users, access tokens, model-provider credentials, admin configuration, or internal telemetry.

## Incident behavior

- Fail closed on authorization, revision, approval, or validation mismatch.
- Preserve the staged proposal for inspection, but do not partially apply it.
- Show a stable public error code and recovery action.
- Keep detailed diagnostics in server-side structured logs with secret redaction; never return them through WebMCP.
- Reset the disposable Challenge Town rather than attempting an unsafe repair during judging.
