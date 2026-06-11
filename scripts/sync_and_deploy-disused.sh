#!/usr/bin/env bash
set -euo pipefail

SERVER="root@119.29.16.170"
REMOTE_DIR="/home/app/freecadai"

echo "=== Syncing code to server (incremental, skipping node_modules/.git/__pycache__) ==="

rsync -avz --delete \
  --exclude 'node_modules' \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '.next' \
  --exclude 'dist' \
  --exclude '*.pyc' \
  --exclude '.env.local' \
  --exclude 'docs' \
  ./ "$SERVER:$REMOTE_DIR/"

echo "=== Running deploy on server ==="
ssh "$SERVER" "bash $REMOTE_DIR/scripts/deploy_on_server.sh"
