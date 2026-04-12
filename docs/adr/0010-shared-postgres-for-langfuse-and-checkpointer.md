# 0010. Shared Postgres for Langfuse and the LangGraph checkpointer

- **Status**: Accepted (with mitigation plan)
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3202 (Data Architecture)

## Context

Two systems in this project need a relational store:

1. **Langfuse** (metadata only — actual traces live in ClickHouse, see ADR-0009)
2. **LangGraph Postgres checkpointer** (`langgraph-checkpoint-postgres`) for session resumability

Both want a Postgres instance. Operating two separate Postgres instances on Railway hobby tier means double the cost, double the backup story, and twice the surface area to monitor — for a learning project that has yet to ship its first production user.

The BRD already flags this as **R3** in the risk register: shared instance has noisy-neighbor risk that's accepted for cost reasons.

## Decision

**One Postgres instance** is shared between Langfuse metadata and the LangGraph checkpointer. Each system uses its own table namespace; no schema collision.

In `docker-compose.yml`:

```yaml
postgres:
  image: postgres:17-alpine
  environment:
    POSTGRES_DB: postgres
```

Both Langfuse (`DATABASE_URL: postgresql://postgres:postgres@postgres:5432/postgres`) and the LangGraph checkpointer (`POSTGRES_URL` env in `Settings`) point at the same database.

A **mitigation plan** with explicit triggers governs when to split.

## Rationale

- **Cost**: one Railway Postgres add-on instead of two. At hobby scale this is the difference between $0 and ~$5/month
- **Operational simplicity**: one instance to back up, one connection pool to size, one set of credentials
- **No actual conflict**: Langfuse uses Prisma-style table names; LangGraph checkpointer uses its own namespace (`checkpoints`, `checkpoint_blobs`, etc.). Schemas don't overlap
- **R3 is a known risk, not an unknown one**: the BRD explicitly accepts it. This ADR makes the trade-off auditable

## Consequences

### Positive
- Single Postgres instance to operate, back up, monitor
- Lower cost
- Single point of recovery for transactional data

### Negative — the trade-off worth knowing

- **Noisy neighbor**: heavy Langfuse trace volume (which writes to Postgres metadata even though traces go to ClickHouse) could starve LangGraph checkpointer queries, or vice versa. Magnitude is unknown until we see real traffic
- **Coupled blast radius**: a bad migration from either system runs against the shared instance. A failed Langfuse upgrade can corrupt LangGraph checkpoints
- **Backup of one tenant requires backing up both**: can't selectively snapshot just Langfuse or just checkpoints
- **Connection pool contention**: two systems competing for the same pool. Both need to be sized down to avoid starvation
- **Cannot scale independently**: if Langfuse trace volume explodes, you can't put it on a beefier instance without also moving the checkpointer

### Mitigation triggers (when to split)

These are the explicit "we should split" signals. If any one fires for more than a week, schedule the split:

| Trigger | Where to watch | Action |
|---|---|---|
| Connection pool wait time > 100 ms p95 | Postgres `pg_stat_activity` query | Split into two instances |
| Either system reports lock contention in logs | App logs (Langfuse worker, LangGraph checkpointer) | Split |
| Postgres CPU > 70% sustained | Railway dashboard | Split |
| Postgres connection count > 80% of `max_connections` | Postgres `pg_stat_activity` | Split |

The split is mechanical: provision a second Postgres instance, point `DATABASE_URL` (Langfuse) at the new one, leave `POSTGRES_URL` (checkpointer) on the old one — or vice versa, whichever is the noisier tenant. No data migration needed (Langfuse can re-bootstrap its schema on first connect; checkpointer state is session-bound and short-lived).

### Neutral / Follow-ups
- The LangGraph checkpointer is **wired as a dependency but not yet activated** in `get_compiled_graph()`. When it's activated (future ADR for "session resumability"), the noisy-neighbor surface area increases. That ADR should re-evaluate this one.
- For prod deployment (M13), consider provisioning the Postgres instance with explicit `max_connections=100` and split the connection pool budget 60/40 between Langfuse and checkpointer.

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **Shared Postgres (one instance, two tenants)** | Cost, simplicity, known trade-off | Noisy-neighbor risk, coupled blast radius | **Selected** — fits hobby-tier budget; risk is acknowledged with mitigation plan |
| Separate Postgres instances from day 1 | No noisy-neighbor risk, independent scaling, independent backups | Double cost, double ops surface | Rejected — premature for hobby scale; can split when triggers fire |
| Use Redis for the LangGraph checkpointer | Faster, no Postgres dep | Loses durability; sessions vanish on restart; defeats checkpointer purpose | Rejected — durability is the whole point |
| In-memory checkpointer (`MemorySaver`) | Zero ops | Sessions lost on every restart | Rejected — no resumability |
| Both in ClickHouse | Single backend | ClickHouse is OLAP, optimized for trace queries; transactional checkpointer workload is the wrong fit | Rejected — ClickHouse is the wrong tool for OLTP |
| SQLite for the checkpointer | Embedded, simple | Doesn't survive Railway redeploys (ephemeral filesystem); single-writer concurrency limits | Rejected — Railway constraints |

## References

- [BRD-01 §7.2 BRD.01.3202](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — Data Architecture topic
- [BRD-01 §10 R3](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — risk register entry for noisy neighbor
- `docker-compose.yml` — Postgres service
- `apps/api/src/config.py.postgres_url` — checkpointer URL
- ADR-0002 — Qdrant for vectors (the third tenant we deliberately did NOT add to Postgres)
- ADR-0009 — Langfuse v3 architecture (which is the "1 of 2 tenants" being shared)
