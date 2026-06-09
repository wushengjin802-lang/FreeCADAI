#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/app/freecadai"

cd "$APP_DIR"

if [ -f docker-compose.prod.yml ]; then
  docker compose -f docker-compose.prod.yml up -d --build
else
  cd "$APP_DIR/deploy"
  docker compose up -d --build
fi

docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep freecadai || true

