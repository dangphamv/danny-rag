---
description: Inspect a recent Langfuse trace by session ID. Pulls the spans for retrieve / rerank / generate / self_grade and summarizes timings, scores, and any errors.
argument-hint: [session_id_or_recent_for_last_5]
allowed-tools: Bash(curl *), Read
---

Inspect Langfuse traces for the RAG pipeline.

Target: $ARGUMENTS

If $ARGUMENTS is empty or `recent`, fetch the 5 most recent traces. Otherwise treat $ARGUMENTS as a session_id and fetch all traces for that session.

## Approach

The Langfuse server is running locally at `http://localhost:3001` (per BRD-01 §3.6). Use the **postgres MCP** (configured in `.mcp.json`) to query the Langfuse Postgres directly — it's faster than the HTTP API for ad-hoc inspection.

Useful tables:
- `traces` — top-level trace records (id, name, user_id, session_id, timestamp, metadata)
- `observations` — spans within a trace (parent_observation_id, name, type, start_time, end_time, input, output, level)
- `scores` — Langfuse score entries (trace_id, name, value, comment)

## Output

For each trace:
```
## Trace {trace_id}  ({session_id})
- Timestamp: ...
- Total latency: Xms
- Spans:
  - rewrite_query    Xms
  - retrieve         Xms   (k=N chunks)
  - rerank           Xms   (top-5)
  - generate         Xms   (Y tokens)
  - self_grade       Xms   (score: 0.XX)
- Scores: thumbs_up=N | thumbs_down=N
- Errors: <none | list>
```

Highlight any span exceeding the per-stage budget:
- retrieve > 200ms
- rerank > 500ms
- generate > 2000ms
- total > 3000ms (the BRD-01 §7.1 p95 floor)

If a trace has level=`ERROR` observations, surface them prominently.
