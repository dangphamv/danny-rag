#!/usr/bin/env bash
# Symmetrical to dev.sh — tear down the entire danny_rag stack:
#   1. api on :8000 (uvicorn)
#   2. web on :3000 (next dev)
#   3. docker compose infra (qdrant + postgres + clickhouse + redis + minio + langfuse-{web,worker})
#
# Volumes (qdrant_data, postgres_data, etc.) are preserved — `docker compose down`
# runs without `-v`. Pass `--wipe` to also drop volumes (requires explicit opt-in).

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIPE=0
for arg in "$@"; do
  case "$arg" in
    --wipe) WIPE=1 ;;
    -h|--help)
      echo "Usage: $0 [--wipe]"
      echo "  --wipe   also delete docker volumes (destructive)"
      exit 0
      ;;
    *)
      echo "[stop] unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

kill_port() {
  local port="$1" label="$2"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    echo "[stop] $label (:$port) — not running"
    return 0
  fi
  echo "[stop] $label (:$port) — TERM pids: $pids"
  kill -TERM $pids 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    sleep 0.3
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    [[ -z "$pids" ]] && { echo "[stop] $label (:$port) — stopped"; return 0; }
  done
  echo "[stop] $label (:$port) — escalating to KILL: $pids"
  kill -KILL $pids 2>/dev/null || true
  sleep 0.3
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "[stop] $label (:$port) — still alive: $pids" >&2
    return 1
  fi
  echo "[stop] $label (:$port) — stopped"
}

kill_port 8000 "api"
kill_port 3000 "web"

echo "[stop] docker compose down$([[ $WIPE -eq 1 ]] && echo " -v")"
if [[ $WIPE -eq 1 ]]; then
  docker compose -f "$ROOT/docker-compose.yml" down -v
else
  docker compose -f "$ROOT/docker-compose.yml" down
fi

remaining="$(lsof -iTCP:8000 -iTCP:3000 -iTCP:6333 -iTCP:5433 -iTCP:3002 -iTCP:6380 -iTCP:8123 -iTCP:9090 -iTCP:9091 -iTCP:3030 -sTCP:LISTEN 2>/dev/null || true)"
if [[ -z "$remaining" ]]; then
  echo "[stop] all project ports clear"
else
  echo "[stop] still listening:" >&2
  echo "$remaining" >&2
  exit 1
fi
