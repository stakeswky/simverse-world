// Barrel for the API layer, split by domain under ./api/ (P1-6 大文件拆分).
// Pure re-exports only — every existing `import ... from '../services/api'`
// call site (values and types) keeps working unchanged.
//
// Note: `./api` resolves to this file (api.ts wins over the api/ directory,
// which intentionally has no index.ts).
export { API_BASE, apiFetch } from './api/core'
export * from './api/forge'
export * from './api/resident'
export * from './api/settings'
export * from './api/social'
export * from './api/world'
export * from './api/economy'
export * from './api/admin'
export * from './api/adminWorld'
export * from './api/decor'
export * from './api/creator'
export * from './api/lab'
export * from './api/townhall'
export * from './api/caravan'
export * from './api/market'
export * from './api/adminHostedAgents'
export * from './api/livingLoop'
