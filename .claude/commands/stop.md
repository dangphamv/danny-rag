---
description: Stop the danny_rag stack — kills the FastAPI backend (:8000), Next.js web (:3000), and brings down docker compose services.
allowed-tools: Bash(lsof *), Bash(kill *), Bash(pkill *), Bash(docker *), Bash(docker compose *)
---

Stop every locally-running piece of the danny_rag stack. Be tolerant of services that are already down — exit cleanly even if nothing was running.

## Steps

1. **Kill the FastAPI backend on :8000** (started via `uv run uvicorn src.main:app --reload`):
   ```
   lsof -ti tcp:8000 | xargs -r kill -TERM
   ```
   If still alive after a moment, escalate to `kill -KILL`.

2. **Kill the Next.js web dev server on :3000** (started via `pnpm dev`):
   ```
   lsof -ti tcp:3000 | xargs -r kill -TERM
   ```
   Same TERM → KILL escalation if needed.

3. **Bring down docker compose services** (qdrant, postgres, clickhouse, redis, minio, langfuse-web, langfuse-worker) from the repo root:
   ```
   docker compose down
   ```
   Do **not** pass `-v` — volumes (`qdrant_data`, `postgres_data`, etc.) must be preserved. If the user explicitly asks to wipe data, confirm first.

4. **Verify** nothing is left listening on the project ports:
   ```
   lsof -iTCP:8000 -iTCP:3000 -iTCP:6333 -iTCP:5433 -iTCP:3002 -sTCP:LISTEN
   ```

## Output

```
## danny_rag stopped
- API (:8000):       ✅ stopped / ⚠️ was not running
- Web (:3000):       ✅ stopped / ⚠️ was not running
- docker compose:    ✅ down (N containers) / ⚠️ already down
- Ports clear:       ✅ / ⚠️ {still-listening list}
```

If any port is still bound after step 4, surface the offending PID + command so the user can deal with it manually.
