#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/app/freecadai"

cd "$APP_DIR"

COMPOSE_FILE="docker-compose.prod.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "[ERROR] $COMPOSE_FILE not found, checking deploy/..."
  COMPOSE_FILE="deploy/docker-compose.yml"
  if [ ! -f "$COMPOSE_FILE" ]; then
    echo "[ERROR] No docker-compose file found."
    exit 1
  fi
fi

echo "=== Stopping existing containers ==="
docker compose -f "$COMPOSE_FILE" down || true

echo "=== Building images ==="
docker compose -f "$COMPOSE_FILE" build --no-cache

echo "=== Starting services ==="
docker compose -f "$COMPOSE_FILE" up -d

echo "=== Waiting for services to be healthy ==="
sleep 5

echo "=== Container status ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep freecadai || true

echo ""
echo "=== API health check ==="
curl -fs http://localhost:8000/health 2>/dev/null || echo "API not ready yet, please wait..."

echo ""
echo "Deploy completed."
