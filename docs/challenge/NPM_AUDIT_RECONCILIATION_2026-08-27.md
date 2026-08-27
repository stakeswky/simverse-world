# npm Audit Reconciliation — Option B Closeout

Generated: 2026-08-27T16:00:00Z  
Starting challenge SHA: `cbbccc50af59380252972590545340f8f4cfc299`  
Evaluated dependency commit: `b4e52d9af4eef0c51cdde6c222079f737114163b`

## Decision

The fresh frontend audit changed from `1 low, 8 high` to
`0 low, 0 moderate, 0 high, 0 critical` without `--force`, overrides, skips, or
suppression. The direct production dependency `react-router-dom` was raised to
`7.18.2`; the direct build dependency Vite was raised to the compatible range
`^8.0.16`, resolving to `8.2.2`. A normal lockfile refresh selected fixed
transitive versions for every remaining finding.

The repository root has no package lock and is therefore not a separate npm
audit target. The authoritative target is `frontend/package-lock.json`.

## Advisory-by-advisory disposition

| Affected node | Before severity | Reachability / dependency path | Fixed selection | Result |
|---|---|---|---|---|
| `@babel/core` | low | Dev/build only through the Vite React/Babel toolchain; not a shipped runtime module. | `7.29.7` | Cleared |
| `brace-expansion` | high | Dev tooling through ESLint/typescript-eslint/minimatch; not in the browser bundle. | `1.1.18` and `5.0.9` for their respective trees | Cleared |
| `js-yaml` | high | Dev tooling configuration parser; not imported by application source. | `4.3.2` | Cleared |
| `nanoid` | high | Build dependency selected under PostCSS/Vite tooling; no application import. | `3.3.18` | Cleared |
| `postcss` | high | Build-time CSS pipeline; processes repository CSS during the trusted build. | `8.5.26` | Cleared |
| `react-router` | high | Production reachable through direct `react-router-dom`; route/navigation runtime. | `7.18.2` | Cleared |
| `react-router-dom` | high | Direct production dependency used by the shipped React routes. | `7.18.2` | Cleared |
| `undici` | high | Dev/test/tooling HTTP client transitive; not imported by browser application source. | `7.29.0` | Cleared |
| `vite` | high | Direct dev/build server and production bundler dependency; its dev server is not deployed, but it is release-critical tooling. | `8.2.2` | Cleared |

## Verification matrix

| Runtime | Install/audit | Tests | Typecheck | ESLint | Build |
|---|---|---:|---|---|---|
| Node `22.23.2`, npm `10.9.8` | `npm ci`; 0 vulnerabilities | 430/430 | pass | 0 errors / 0 warnings | pass |
| Node `24.20.0`, npm `11.19.0` | `npm ci`; 0 vulnerabilities | 430/430 | pass | 0 errors / 0 warnings | pass |

The enabled production build (`VITE_WEBMCP_ENABLED=true`) also passed. npm 11
reported that optional macOS `fsevents` install scripts had not been explicitly
approved by its new install-script policy; the install, tests, lint, typecheck,
audit, and build all completed successfully. This is retained as a non-blocking
tooling notice rather than hidden.

## Evidence

- Before JSON: `/tmp/simverse-option-b-closeout/npm-audit-before.json`
- After JSON: `/tmp/simverse-option-b-closeout/npm-audit-after.json`
- Final JSON: `/tmp/simverse-option-b-closeout/npm-audit-final.json`
- Node 22 matrix: `/tmp/simverse-option-b-closeout/frontend-node22-after-upgrade.log`
- Node 24 matrix: `/tmp/simverse-option-b-closeout/frontend-node24-after-upgrade.log`

