#!/usr/bin/env bash
set -euo pipefail

# Deploy backend to remote server via SSH + Docker Compose
# Usage: ./deploy.sh [user@host]

REMOTE="${1:-root@100.93.72.102}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/../.."
BACKEND_DIR="$PROJECT_DIR/.worktrees/mvp-implementation/backend"
REMOTE_DIR="/opt/skills-world"

echo "==> Syncing backend to $REMOTE:$REMOTE_DIR..."
ssh "$REMOTE" "mkdir -p $REMOTE_DIR/backend $REMOTE_DIR/deploy"

# Sync backend code
rsync -avz --delete \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '*.pyc' \
  --exclude 'data/' \
  "$BACKEND_DIR/" "$REMOTE:$REMOTE_DIR/backend/"

# Sync deploy configs
rsync -avz \
  "$SCRIPT_DIR/docker-compose.yml" \
  "$SCRIPT_DIR/Dockerfile" \
  "$REMOTE:$REMOTE_DIR/deploy/"

# Check if .env exists on remote, if not copy example
ssh "$REMOTE" "test -f $REMOTE_DIR/deploy/.env || echo 'WARNING: No .env file found. Copy .env.example and fill in values.'"

echo "==> Building and starting services on $REMOTE..."
ssh "$REMOTE" "cd $REMOTE_DIR/deploy && docker compose up -d --build"

echo "==> Checking health..."
sleep 3
ssh "$REMOTE" "curl -sf http://localhost:8000/health && echo ' ✓ API healthy' || echo ' ✗ API not responding'"

echo "==> Done!"
