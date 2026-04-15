#!/usr/bin/env bash
set -euo pipefail

# Deploy frontend to Cloudflare Workers
# Usage: VITE_API_URL=https://api.example.com ./deploy.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../../frontend"

echo "==> Building frontend..."
cd "$FRONTEND_DIR"
npm ci
VITE_API_URL="${VITE_API_URL:?Set VITE_API_URL to your backend URL}" npm run build

echo "==> Copying dist to deploy dir..."
rm -rf "$SCRIPT_DIR/dist"
cp -r "$FRONTEND_DIR/dist" "$SCRIPT_DIR/dist"

echo "==> Deploying to Cloudflare Workers..."
cd "$SCRIPT_DIR"
npx wrangler deploy

echo "==> Done!"
