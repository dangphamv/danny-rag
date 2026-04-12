#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/.dev-logs"
mkdir -p "$LOG_DIR"

cleanup() {
  echo ""
  echo "[dev] stopping..."
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "[dev] stopped. (docker compose still running — run 'docker compose down' to stop infra)"
}
trap cleanup EXIT INT TERM

echo "[dev] starting infra (qdrant + postgres + langfuse)..."
docker compose -f "$ROOT/docker-compose.yml" up -d

echo "[dev] starting api on :8000 (logs: $LOG_DIR/api.log)"
( cd "$ROOT/apps/api" && uv run uvicorn src.main:app --reload --port 8000 ) \
  > "$LOG_DIR/api.log" 2>&1 &
API_PID=$!

echo "[dev] starting web on :3000 (logs: $LOG_DIR/web.log)"
( cd "$ROOT/apps/web" && pnpm dev ) \
  > "$LOG_DIR/web.log" 2>&1 &
WEB_PID=$!

echo ""
echo "[dev] api pid=$API_PID  web pid=$WEB_PID"
echo "[dev] tail logs:  tail -f $LOG_DIR/api.log $LOG_DIR/web.log"
echo "[dev] ctrl-c to stop api + web"
wait
