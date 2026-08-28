# Day-0 Public WebMCP Live Gate

Verified on 2026-08-27 against the exact public deployment of commit `ac8d98fa2d06776819a80c9e22e604e846b0730a` (tree `5b6915f3537c2268f8904bdb459217b98efe8cc0`) at `https://simverse.world/challenge`.

## Deployment identity

- Cloudflare Worker version: `a8cce985-3d28-4ff6-9bd8-493674aca1ca`
- Entry asset: `/assets/index-DOrHmXt5.js`
- Entry SHA-256: `19c1407a1df8ab70e55aeb87aaf7a5be69b38103b2cd6e1427ff7a914c45f95d`
- Challenge asset: `/assets/ChallengePage-DSk8jcOy.js`
- Challenge SHA-256: `eeba3a713692087813ed15c48bb7a7ea2dee35bb1898c75fb4cea9b853b943b8`
- Public tool: exactly one `simverse_get_challenge_status`
- Tool input: strict empty object with `additionalProperties: false`
- Tool result: exactly `resettable`, `scenario`, `tool_version`, `town`, and `world_time`

## Live matrix

| Host | Version | Run | Commit | Entry asset | Challenge asset | Discover | Invoke | Receipt | Approval expiry | Session expiry | Refresh | Back/Forward | BFCache | Ordinary fallback | Duplicate tools | Evidence |
|---|---|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ChatGPT in-app Browser | ChatGPT Desktop 26.820.60940; Chromium 151.0.0.0; `gpt-5.6-sol` | 1 | `ac8d98f` | `index-DOrHmXt5.js` | `ChallengePage-DSk8jcOy.js` | PASS, exact one tool | PASS, five-field result | PASS, visible `Completed in 0 ms` | N/A — Day-0 status probe | N/A — Day-0 status probe | PASS, 1 tool and callable | PASS, 1→0→1→0→1 | PASS, fresh-loader fallback restored the exact surface | N/A | 0 | `/tmp/simverse-option-b-chatgpt-iab-run1.png`, SHA-256 `4b2ff2ed0674376714854bc224703cc32a48128fd87f0a53848bb58c074acaa9` |
| ChatGPT in-app Browser | ChatGPT Desktop 26.820.60940; Chromium 151.0.0.0; `gpt-5.6-sol` | 2 | `ac8d98f` | `index-DOrHmXt5.js` | `ChallengePage-DSk8jcOy.js` | PASS, exact one tool | PASS, five-field result | PASS, visible `Completed in 0 ms` | N/A — Day-0 status probe | N/A — Day-0 status probe | PASS, 1 tool and callable | PASS, 1→0→1→0→1 | PASS, fresh-loader fallback restored the exact surface | N/A | 0 | `/tmp/simverse-option-b-chatgpt-iab-run2.png`, SHA-256 `259e46507f28515bfd0dad1dd29e6c1c3048f87f9434e1665c2606d385dc2814` |
| ChatGPT in-app Browser | ChatGPT Desktop 26.820.60940; Chromium 151.0.0.0; `gpt-5.6-sol` | 3 | `ac8d98f` | `index-DOrHmXt5.js` | `ChallengePage-DSk8jcOy.js` | PASS, exact one tool | PASS, five-field result | PASS, visible `Completed in 0 ms` | N/A — Day-0 status probe | N/A — Day-0 status probe | PASS, 1 tool and callable | PASS, 1→0→1→0→1 | PASS, fresh-loader fallback restored the exact surface | N/A | 0 | `/tmp/simverse-option-b-chatgpt-iab-run3.png`, SHA-256 `a753375f6c68f7945366d04aa9927790f598e11247c367ec5e2e9ac79515f266` |
| Chrome for Testing | 149.0.7827.155 | 1 | `ac8d98f` | `index-DOrHmXt5.js` | `ChallengePage-DSk8jcOy.js` | PASS, exact one tool | PASS, five-field result | PASS, visible completion | N/A — Day-0 status probe | N/A — Day-0 status probe | PASS | PASS, 1→0→1→0→1 | PASS, `pageshow.persisted=true` | N/A | 0 | `/tmp/simverse-option-b-chrome149-public-run1.png`, SHA-256 `262b56c8b0cc26da782f7c43566bb4752a5a8ea52b2bf72d35466f56918df1aa`, 3476 ms |
| Chrome for Testing | 149.0.7827.155 | 2 | `ac8d98f` | `index-DOrHmXt5.js` | `ChallengePage-DSk8jcOy.js` | PASS, exact one tool | PASS, five-field result | PASS, visible completion | N/A — Day-0 status probe | N/A — Day-0 status probe | PASS | PASS, 1→0→1→0→1 | PASS, `pageshow.persisted=true` | N/A | 0 | `/tmp/simverse-option-b-chrome149-public-run2.png`, SHA-256 `9604c4be3e14d8dcd267c4dfb9fe351b3f4d4d41bc01e6d2eb07a14f6c9e96a5`, 2854 ms |
| Chrome for Testing | 149.0.7827.155 | 3 | `ac8d98f` | `index-DOrHmXt5.js` | `ChallengePage-DSk8jcOy.js` | PASS, exact one tool | PASS, five-field result | PASS, visible completion | N/A — Day-0 status probe | N/A — Day-0 status probe | PASS | PASS, 1→0→1→0→1 | PASS, `pageshow.persisted=true` | N/A | 0 | `/tmp/simverse-option-b-chrome149-public-run3.png`, SHA-256 `1ca1036a2d199231241a8b0ecb4bccb0be12b44679a77095aefeabd6e6a00cd0`, 3248 ms |
| Ordinary Chrome | 151.0.7922.174, fresh profile | 1 | `ac8d98f` | `index-DOrHmXt5.js` | `ChallengePage-DSk8jcOy.js` | N/A, no modelContext surface | N/A | PASS, full page and explicit unavailable state | N/A — Day-0 status probe | N/A — Day-0 status probe | PASS | PASS | N/A | PASS, no console or page errors and no false readiness claim | 0 | `/tmp/simverse-option-b-ordinary-fallback.png`, SHA-256 `6c2e75d38a1a0b798340e744563c0faf319c95c947f8a5a402556e37532a0a45` |

## ChatGPT lifecycle evidence

- Run 1: direct discover/call plus full-document leave, Back, Forward, second Back, refresh/call, same-document Challenge→Town, and Back all passed. The structured matrix returned tool counts `1→0→1→0→1`, refresh `1`, same-document leave `0`, and same-document Back `1`.
- Run 2: `2026-08-27T02:15:00.457Z` to `2026-08-27T02:15:11.822Z`; the same lifecycle and five-field result passed.
- Run 3: `2026-08-27T02:15:24.098Z` to `2026-08-27T02:15:36.573Z`; the same lifecycle and five-field result passed.
- A separate CDP read-only loader probe confirmed the in-app Browser did not reuse the old document loader during its full-document history traversal. Each fresh document still exposed the correct count (`Challenge=1`, `Town=0`) with no stale or duplicate registrations.
- Three evidence captures were produced after a fresh reload and one successful read-only invocation each. Every capture contained `Site Tool ready`, Agent Activity `1`, and `Completed in 0 ms`.

## Gate result

`day0_chatgpt=3/3 chrome149=3/3 ordinary_fallback=1/1 duplicate_tools=0 stale_tools=0`

Phase 0 is green. Approval and session expiry are deliberately not claimed for this fixed Day-0 read-only status probe.
