#!/usr/bin/env bash
set -euo pipefail

simverse_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
simverse_spec="${1:-e2e/challenge-flow.spec.ts}"
simverse_api_log=/tmp/simverse-option-b-api.log
simverse_frontend_log=/tmp/simverse-option-b-frontend.log
simverse_playwright_log=/tmp/simverse-option-b-playwright.log
simverse_evidence_log=/tmp/simverse-option-b-e2e-evidence.log
simverse_api_pid_file=/tmp/simverse-option-b-api.pid
simverse_frontend_pid_file=/tmp/simverse-option-b-frontend.pid
simverse_api_drain=/tmp/simverse-option-b-api.drained
simverse_frontend_drain=/tmp/simverse-option-b-frontend.drained
simverse_preexisting=/tmp/simverse-option-b-preexisting-services.txt
simverse_artifacts=/tmp/simverse-option-b-e2e-artifacts
simverse_api_pid=""
simverse_frontend_pid=""

if [[ ! "$simverse_spec" =~ ^e2e/challenge-[a-z-]+\.spec\.ts$ ]]; then
  printf 'invalid Playwright spec: %s\n' "$simverse_spec" >&2
  exit 64
fi

cd "$simverse_root"

if [[ -d /opt/homebrew/opt/node@22/bin ]]; then
  export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
fi
export NO_PROXY=localhost,127.0.0.1,::1
export no_proxy="$NO_PROXY"
if [[ "$(node -p 'process.versions.node.split(`.`)[0]')" != 22 ]]; then
  printf 'Node major 22 is required; found %s\n' "$(node --version)" >&2
  exit 65
fi

for simverse_port in 8000 4173; do
  if lsof -nP -iTCP:"$simverse_port" -sTCP:LISTEN >/dev/null 2>&1; then
    printf 'required port %s is already in use\n' "$simverse_port" >&2
    lsof -nP -iTCP:"$simverse_port" -sTCP:LISTEN >&2
    exit 66
  fi
done

rm -f \
  "$simverse_api_log" \
  "$simverse_frontend_log" \
  "$simverse_playwright_log" \
  "$simverse_evidence_log" \
  "$simverse_api_pid_file" \
  "$simverse_frontend_pid_file" \
  "$simverse_api_drain" \
  "$simverse_frontend_drain" \
  "$simverse_preexisting" \
  "$simverse_artifacts/challenge-full-flow-10.png" \
  "$simverse_artifacts/challenge-reset-10.png" \
  "$simverse_artifacts/challenge-outcome-prediction.png" \
  "$simverse_artifacts/challenge-outcome-actual.png" \
  "$simverse_artifacts/challenge-outcome-control.png" \
  "$simverse_artifacts/report.json"
mkdir -p "$simverse_artifacts"

stop_owned_process() {
  local simverse_label="$1"
  local simverse_pid="$2"
  local simverse_pattern="$3"
  local simverse_sentinel="$4"
  if [[ -z "$simverse_pid" ]]; then
    printf '%s not-started\n' "$simverse_label" >"$simverse_sentinel"
    return
  fi
  if ! kill -0 "$simverse_pid" >/dev/null 2>&1; then
    wait "$simverse_pid" >/dev/null 2>&1 || true
    printf '%s already-exited\n' "$simverse_label" >"$simverse_sentinel"
    return
  fi
  local simverse_command
  simverse_command="$(ps -p "$simverse_pid" -o command= 2>/dev/null || true)"
  if [[ ! "$simverse_command" =~ $simverse_pattern ]]; then
    printf '%s pid mismatch: %s\n' "$simverse_label" "$simverse_command" >&2
    return 1
  fi
  kill "$simverse_pid"
  for _ in {1..50}; do
    if ! kill -0 "$simverse_pid" >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
  if kill -0 "$simverse_pid" >/dev/null 2>&1; then
    kill -9 "$simverse_pid"
  fi
  wait "$simverse_pid" >/dev/null 2>&1 || true
  printf '%s drained pid=%s\n' "$simverse_label" "$simverse_pid" >"$simverse_sentinel"
}

cleanup() {
  local simverse_cleanup_rc=0
  stop_owned_process \
    frontend "$simverse_frontend_pid" 'npm run preview|vite preview' \
    "$simverse_frontend_drain" || simverse_cleanup_rc=1
  stop_owned_process \
    api "$simverse_api_pid" 'uvicorn app\.main:app' \
    "$simverse_api_drain" || simverse_cleanup_rc=1
  return "$simverse_cleanup_rc"
}
trap 'cleanup || true' EXIT INT TERM

docker compose ps --status running --services >"$simverse_preexisting"
docker compose up -d db redis

for _ in {1..120}; do
  if docker compose exec -T db pg_isready -U postgres -d skills_world >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
docker compose exec -T db pg_isready -U postgres -d skills_world

for _ in {1..120}; do
  if [[ "$(docker compose exec -T redis redis-cli ping 2>/dev/null || true)" == PONG ]]; then
    break
  fi
  sleep 0.5
done
test "$(docker compose exec -T redis redis-cli ping)" = PONG

if [[ ! -x backend/.venv/bin/python ]]; then
  python3.12 -m venv backend/.venv
fi
(
  cd backend
  .venv/bin/pip install -e '.[dev]'
)
(
  cd backend
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/skills_world \
    DEBUG=true \
    .venv/bin/alembic upgrade head
)

DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/skills_world \
REDIS_URL=redis://localhost:6379/15 \
DEBUG=true \
RUN_BACKGROUND_TASKS=false \
AUTO_CREATE_TABLES=false \
CORS_ORIGINS='["http://localhost:4173"]' \
CHALLENGE_ALLOWED_ORIGINS='["http://localhost:4173"]' \
  backend/.venv/bin/uvicorn app.main:app \
    --app-dir backend --host 127.0.0.1 --port 8000 \
    >"$simverse_api_log" 2>&1 &
simverse_api_pid=$!
printf '%s\n' "$simverse_api_pid" >"$simverse_api_pid_file"

for _ in {1..120}; do
  if curl -fsS --max-time 5 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$simverse_api_pid" >/dev/null 2>&1; then
    tail -120 "$simverse_api_log" >&2
    exit 67
  fi
  sleep 0.5
done
curl -fsS --max-time 5 http://127.0.0.1:8000/health >/dev/null

(
  cd frontend
  npm ci
  npx playwright install chromium
  VITE_WEBMCP_ENABLED=true VITE_API_URL=http://localhost:8000 npm run build
)

(
  cd frontend
  exec npm run preview -- --host localhost --port 4173
) >"$simverse_frontend_log" 2>&1 &
simverse_frontend_pid=$!
printf '%s\n' "$simverse_frontend_pid" >"$simverse_frontend_pid_file"

for _ in {1..120}; do
  if curl -fsS --max-time 5 http://localhost:4173/challenge >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$simverse_frontend_pid" >/dev/null 2>&1; then
    tail -120 "$simverse_frontend_log" >&2
    exit 68
  fi
  sleep 0.5
done
curl -fsS --max-time 5 http://localhost:4173/challenge >/dev/null

set +e
(
  cd frontend
  npx playwright test "$simverse_spec" --project=chromium
) 2>&1 | tee "$simverse_playwright_log"
simverse_test_rc=${PIPESTATUS[0]}
set -e

simverse_cleanup_rc=0
cleanup || simverse_cleanup_rc=$?
trap - EXIT INT TERM

{
  printf 'recorded_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'source_head=%s\n' "$(git rev-parse HEAD)"
  printf 'source_subject=%s\n' "$(git show -s --format=%s HEAD)"
  printf 'command=bash scripts/run-challenge-e2e.sh %s\n' "$simverse_spec"
  printf 'node=%s npm=%s playwright=%s\n' \
    "$(node --version)" "$(npm --version)" \
    "$(cd frontend && npx playwright --version)"
  printf 'preexisting_services:\n'
  sed 's/^/  /' "$simverse_preexisting"
  printf 'playwright_exit=%s cleanup_exit=%s\n' \
    "$simverse_test_rc" "$simverse_cleanup_rc"
  printf 'api_health=ok frontend_health=ok\n'
  printf 'api_drain=%s\n' "$(cat "$simverse_api_drain" 2>/dev/null || true)"
  printf 'frontend_drain=%s\n' "$(cat "$simverse_frontend_drain" 2>/dev/null || true)"
  printf 'playwright_output:\n'
  sed 's/^/  /' "$simverse_playwright_log"
  printf 'api_log_tail:\n'
  tail -80 "$simverse_api_log" | sed 's/^/  /'
  printf 'frontend_log_tail:\n'
  tail -80 "$simverse_frontend_log" | sed 's/^/  /'
} >"$simverse_evidence_log"

if [[ "$simverse_test_rc" != 0 || "$simverse_cleanup_rc" != 0 ]]; then
  cat "$simverse_evidence_log"
  exit 1
fi
test -s "$simverse_api_drain"
test -s "$simverse_frontend_drain"
test -s "$simverse_artifacts/challenge-full-flow-10.png"
test -s "$simverse_artifacts/challenge-reset-10.png"
test -s "$simverse_artifacts/challenge-outcome-prediction.png"
test -s "$simverse_artifacts/challenge-outcome-actual.png"
test -s "$simverse_artifacts/challenge-outcome-control.png"
test -s "$simverse_artifacts/report.json"
rg -Fx \
  'full_flow=10/10 reset_hash=10/10 replay_success=0 unauthorized_success=0 duplicate_tools=0' \
  "$simverse_playwright_log" >/dev/null

printf '%s\n' \
  'full_flow=10/10 reset_hash=10/10 replay_success=0 unauthorized_success=0 duplicate_tools=0'
