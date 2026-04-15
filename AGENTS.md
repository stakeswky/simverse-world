# Repository Guidelines

## Project Structure & Module Organization
This repo is split into `backend/` and `frontend/`. The FastAPI app lives in `backend/app/`, with domain folders such as `agent/`, `memory/`, `personality/`, `routers/`, and `services/`. Database migrations are in `backend/alembic/`, and backend tests live in `backend/tests/` as `test_<feature>.py`. The React + Vite client lives in `frontend/src/`, with UI in `components/`, routes in `pages/`, game code in `game/`, shared state in `stores/`, API helpers in `services/`, and static assets in `frontend/public/`. Design notes and screenshots are stored under `docs/`; deployment files live in `deploy/`.

## Build, Test, and Development Commands
Start local infra from the repo root with `docker compose up -d`. For the backend: `cd backend && pip install -e ".[dev]"`, `alembic upgrade head`, then `uvicorn app.main:app --reload --port 8000`. Run backend tests with `cd backend && python3 -m pytest tests/`. For the frontend: `cd frontend && npm install`, `npm run dev` for local development, `npm run build` for production output, `npm run lint` for ESLint, and `npx tsc --noEmit` for a direct type check.

## Coding Style & Naming Conventions
Follow existing conventions instead of introducing new patterns. Python uses 4-space indentation, snake_case modules, and domain-grouped files such as `routers/auth.py` or `services/sbti_service.py`. TypeScript/React uses 2-space indentation, PascalCase for components and pages (`GamePage.tsx`), and camelCase for utilities and stores (`gameStore.ts`). Keep files close to the feature they serve. Frontend linting is handled by `frontend/eslint.config.js`; no separate Python formatter is configured here, so keep backend edits small and consistent with surrounding code.

## Testing Guidelines
Backend coverage is pytest-based, with many async tests using `@pytest.mark.anyio`. Add or update regression tests in `backend/tests/` whenever backend behavior changes, especially for agent, memory, forge, or API routes. There is no dedicated frontend test runner in this repo today, so frontend PRs should at minimum pass `npm run lint`, `npm run build`, and `npx tsc --noEmit`.

## Commit & Pull Request Guidelines
Recent history follows scoped Conventional Commits, for example `feat(agent): ...`, `fix(test): ...`, and `test(agent): ...`. Keep that format and use imperative summaries. PRs should stay focused, describe user-visible behavior, list verification commands run, call out schema or `.env` changes, and include screenshots for UI changes.

## Security & Configuration Tips
Use the checked-in examples: `backend/.env.example`, `frontend/.env.example`, and `deploy/backend/.env.example`. Do not commit secrets, generated `.env` files, or local deployment state.
