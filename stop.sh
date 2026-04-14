#!/usr/bin/env bash
# Stop every locally-running piece of the danny_rag stack:
#   - FastAPI backend on :8000 (and stray uvicorn dev ports :8001, :8002)
#   - Next.js web dev server on :3000
#   - docker compose services (qdrant, postgres, clickhouse, redis, minio, langfuse-web, langfuse-worker)
#
# Tolerant of already-down services. Preserves docker volumes (no `-v`).
set -u

cd "$(dirname "$0")"

PORTS=(8000 8001 8002 3000)
API_STATUS="was not running"
ALT_API_STATUS=""
WEB_STATUS="was not running"

kill_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti "tcp:${port}" 2>/dev/null || true)
  if [[ -z "${pids}" ]]; then
    return 1
  fi
  echo "${pids}" | xargs kill -TERM 2>/dev/null || true
  sleep 1
  pids=$(lsof -ti "tcp:${port}" 2>/dev/null || true)
  if [[ -n "${pids}" ]]; then
    echo "${pids}" | xargs kill -KILL 2>/dev/null || true
  fi
  return 0
}

if kill_port 8000; then
  API_STATUS="stopped"
fi
for alt in 8001 8002; do
  if kill_port "${alt}"; then
    ALT_API_STATUS="${ALT_API_STATUS}${alt} "
  fi
done
if kill_port 3000; then
  WEB_STATUS="stopped"
fi

COMPOSE_STATUS="already down"
if docker compose ps --status running --quiet 2>/dev/null | grep -q .; then
  docker compose down >/dev/null 2>&1 && COMPOSE_STATUS="down"
fi

STILL_LISTENING=""
for port in "${PORTS[@]}" 6333 5433 3002; do
  if lsof -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1; then
    STILL_LISTENING="${STILL_LISTENING}${port} "
  fi
done

echo "## danny_rag stopped"
echo "- API (:8000):     ${API_STATUS}"
if [[ -n "${ALT_API_STATUS}" ]]; then
  echo "- Dev API ports:   stopped (${ALT_API_STATUS% })"
fi
echo "- Web (:3000):     ${WEB_STATUS}"
echo "- docker compose:  ${COMPOSE_STATUS}"
if [[ -n "${STILL_LISTENING}" ]]; then
  echo "- Ports clear:     STILL LISTENING: ${STILL_LISTENING% }"
  exit 1
fi
echo "- Ports clear:     yes"
