---
description: Ingest a test document via the CLI, verify it lands in Qdrant, then re-ingest to prove idempotency (MTC-02).
argument-hint: [path/to/document.pdf]
allowed-tools: Bash(cd apps/api && uv run *), Bash(curl *), Read
---

Test the ingestion pipeline against a single document and prove idempotency.

Document: $ARGUMENTS

If $ARGUMENTS is empty, fail with: "Provide a path to a document, e.g. `/ingest-test data/sample.pdf`".

## Steps

1. **Pre-count** — query Qdrant for current point count in the active collection:
   ```
   curl -s http://localhost:6333/collections/{collection}/points/count
   ```
   (Determine `{collection}` from `apps/api/src/config.py` defaults — it's derived from `EMBED_PROVIDER`.)

2. **First ingest** — `cd apps/api && uv run python -m src.ingestion.cli $ARGUMENTS`. Capture chunk count from the log.

3. **Post-count after first** — query Qdrant again. Delta should equal the logged chunk count.

4. **Second ingest** — `cd apps/api && uv run python -m src.ingestion.cli $ARGUMENTS` again, no other changes.

5. **Post-count after second** — query Qdrant again. **Delta MUST be zero** (idempotency, MTC-02).

6. **Report**:
   ```
   ## Ingest test — {document}
   - Pre-count:    N
   - After 1st:    N + K  (logged chunks: K)
   - After 2nd:    N + K  (idempotent: ✅ / ❌)
   - Verdict:      PASS / FAIL — content_hash dedupe broken
   ```

If idempotency fails, delegate the root-cause investigation to the `ingestion-debugger` subagent.
