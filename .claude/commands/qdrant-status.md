---
description: Dump local Qdrant status — collections, dimensions, point counts, and config sanity checks against MTC-01 / MTC-11.
allowed-tools: Bash(curl *)
---

Inspect the local Qdrant instance running at `http://localhost:6333` and report status.

## Steps

1. **Health**:
   ```
   curl -s http://localhost:6333/readyz
   ```

2. **List collections**:
   ```
   curl -s http://localhost:6333/collections | jq '.result.collections'
   ```

3. **For each collection**, get the config and point count:
   ```
   curl -s http://localhost:6333/collections/{name}
   curl -s http://localhost:6333/collections/{name}/points/count
   ```

4. **Sanity checks** against BRD-01 §3.7:
   - **MTC-01**: each collection name should encode the embedder (e.g., `chunks_text-embedding-3-small`, `chunks_nomic-embed-text`). Flag collections without an embedder identifier.
   - **MTC-11**: collections using `text-embedding-3-small` must have `vectors.size == 1536`. Collections using `nomic-embed-text` must have `vectors.size == 768`. Flag dimension mismatches.

## Output

```
## Qdrant status @ localhost:6333
- Health: ✅ / ❌
- Collections:
  - {name}: dim=N, points=K, distance={cosine|dot|euclid}, status={green|yellow|red}
  - ...

### Sanity (MTC-01 / MTC-11)
- ✅ All collection names encode the embedder
- ✅ All dimensions match their embedder
- (or ⚠️ findings)
```

If Qdrant is not reachable, suggest `docker compose up -d qdrant`.
