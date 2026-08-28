# Challenge Security and Authority Boundary

Threat statement: Untrusted Site Tool input or page evidence must never create, widen, or replay a human approval capability.

The anonymous Challenge experience is useful only if the agent can investigate and execute the exact action a person approved, without gaining invisible authority. All state is confined to a disposable, deterministic Challenge Town that cannot address production town data.

## Trust boundary

| Input or actor | Trust | Allowed authority |
|---|---|---|
| Crisis evidence and tool results | Untrusted content | Inform investigation; never choose capabilities or tool registration |
| Site Tool arguments | Untrusted structured input | Select only allowlisted public IDs and exact expected versions/hashes |
| Ordinary UI or Site Tool preview | Non-authorizing | Create an immutable diff and forecast; never mutate the world |
| Visible human approval control | Trusted browser ceremony | Mint one server-bound, short-lived, one-time capability for one exact diff |
| Commit endpoint | Server authority | Consume that capability only when every binding still matches |

A Site Tool cannot submit an approval ID, create approval, or widen the approved action. A privileged computer-use agent could click the same visible control a human can click, so the product makes that action explicit and legible; the security claim is capability binding and one-time consumption, not mind-reading who physically clicked.

## Mutation checks

Every mutation request must pass all of these checks before state changes:

1. Exact HTTPS `Origin` allowlist and a browser session cookie scoped to Challenge routes.
2. Double-submit `CSRF` validation, with neither token returned through a Site Tool result.
3. Public schema allowlists and strict rejection of extra, missing, mistyped, or out-of-range fields.
4. Exact binding to `preview_id`, `diff_hash`, `world_version`, session generation, scenario, and fixture version.
5. Server-side approval lookup; no caller-supplied approval capability is accepted.
6. Redis `WATCH` plus CAS semantics so concurrent commits cannot consume the same approval or advance the same world twice.
7. Expiry, one-time consumption, idempotency, and replay rejection.
8. A receipt that binds the before/after versions and hashes without exposing secret material.

On any mismatch, the backend fails closed with a stable public error. It never partially applies the diff and never trusts a stale preview.

## Lifecycle confinement

- The initial fixture is locked at public v7 and has a documented public hash.
- Preview is read-only and leaves the world at v7.
- Commit advances exactly to v8 and applies exactly `-240 SC`.
- Verification advances exactly 72 hours to v9 and evaluates 13 time points.
- Reset replaces the anonymous generation and restores v7 and the locked hash.
- Expired, failed, committed, or verified sessions expose only the state-appropriate catalogue.
- Route departure aborts the old surface; a host that cannot prove removal fails closed instead of mixing tool generations.

## Public output boundary

Site Tool results contain only allowlisted fictional Challenge Town fields. They never include cookies, CSRF values, JWT/Authorization data, approval identifiers, server-only hashes, Redis keys, internal URLs, stack traces, private resident text, account data, model-provider credentials, or internal telemetry.

Activity telemetry remains browser-session memory only. It records the fixed event vocabulary and safe timing/count fields; it is not uploaded by the Challenge feature.

## Diagnostics-only status probe

The legacy `simverse_get_challenge_status` probe is lazy-loaded only for a human-opened `/challenge?diagnostics=1` page. It is read-only, returns the same fixed public status shown on that diagnostics page, and is excluded from the ordinary five-tool catalogue and hero-flow claims.

## Incident behavior

- Preserve a rejected preview for visible inspection, but do not mutate anything.
- Return a stable public code and recovery action; keep raw exceptions server-side with secret redaction.
- Prefer resetting the disposable Challenge Town over attempting an unsafe repair during judging.
- Treat duplicate, stale, mixed-generation, or replayed capabilities as security failures, not retryable success paths.
