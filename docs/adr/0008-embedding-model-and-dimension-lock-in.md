# 0008. Embedding model and dimension lock-in

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3206 (AI/ML), MTC-01, MTC-11

## Context

Embedding model choice has lasting consequences. Vector dimensions are baked into the Qdrant collection at creation time, and switching models requires:

1. Creating a new collection with the new dimension
2. Re-embedding the entire corpus
3. Re-running ingestion against the new collection
4. Cutting traffic over (no in-place migration)

The worst failure mode here is **silent corruption from mixing dimensions**: if you embed with model A (1536d) and then queries hit a collection that contains some chunks from model B (768d), the cosine similarity scores are mathematically meaningless and retrieval quality silently degrades. There's no error, no warning — just bad answers.

## Decision

**`text-embedding-3-small` (1536d) is the locked primary embedder.** It is the platform default for all production retrieval. Hardcoded:

- `Settings.embed_provider` defaults to `"openai"`
- `Settings.embedding_dimension` returns 1536 for `openai`
- `Settings.qdrant_collection` returns `"chunks_text-embedding-3-small"`
- `OpenAIEmbedder.__init__` hardcodes `1536` for `text-embedding-3-small`

**One Qdrant collection per embedding model** (MTC-01). Switching `EMBED_PROVIDER=ollama` selects a different collection (`chunks_nomic-embed-text` at 768d) — never the same collection as the OpenAI embedder. This makes dimension mixing impossible by construction.

**Switching the primary embedder requires a new ADR.** It is not a config knob. The `CLAUDE.md` rules and the `security-auditor` subagent both enforce this.

## Rationale

- **`text-embedding-3-small` is the cost/quality sweet spot** in the OpenAI embedding family. At $0.02 per million tokens, embedding 100k chunks costs about $0.10. The larger `text-embedding-3-large` is 4× the cost for marginal quality lift on hobby-scale corpora.
- **1536d is the right size**: small enough that Qdrant Cloud's free 1 GB tier holds ~500k chunks (10× our MVP needs), large enough that retrieval quality is good
- **One-collection-per-embedder is the only safe rule**: any other rule (mix dimensions, version-tag chunks, runtime dispatch) opens the silent-corruption door. Better to make it structurally impossible
- **Lock-in is structural, not soft**: the dimension is hardcoded in `OpenAIEmbedder.__init__`, encoded in the collection name, asserted in `pipeline.py:ingest_document` (`if embedder.dimension != settings.embedding_dimension: raise`). Three independent guardrails
- **ADR-required gate** is the right ergonomic friction. Switching embedders is a meaningful architectural change deserving documented reasoning, not an env-var flip

## Consequences

### Positive
- Silent dimension-mix corruption is impossible by construction
- Migration cost is *known* (one-shot re-ingestion of the corpus) rather than *uncertain* (debugging weird retrieval results)
- The `security-auditor` subagent's MTC-11 check is a one-line grep
- Hobby-tier costs stay predictable

### Negative
- **Cannot A/B test embedders** without re-ingestion. Want to know if `bge-small-en-v1.5` would work better? You have to embed the whole corpus into a new collection and run the eval suite against both. There's no shortcut
- **Migration is binary**: you can't gradually roll out a new embedder
- **Hardcoded dimensions** mean adding a third primary model requires a code change in `OpenAIEmbedder.__init__` (and an ADR)
- **Locked to OpenAI as the primary embedder** = vendor relationship, even if the chat LLM is Anthropic

### Neutral / Follow-ups
- The local Ollama embedder (`nomic-embed-text`, 768d) lives in its own collection (`chunks_nomic-embed-text`) and is for offline experimentation only — never primary
- If `text-embedding-3-small` is ever deprecated, the migration path is documented in this ADR's "Negative" section: re-embed the corpus into a new collection, swap the env var, drop the old collection
- A future ADR could add `text-embedding-3-large` as a quality-mode alternative for premium use cases — but only if eval data justifies the 4× cost

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **`text-embedding-3-small` (1536d) locked, one-collection-per-embedder** | Cost/quality sweet spot, small collection footprint, structural safety against dim mixing | Vendor lock, can't A/B test | **Selected** — best fit for the constraints |
| `text-embedding-3-large` (3072d) | Higher quality | 4× cost, 2× storage, marginal lift at hobby scale | Rejected — wrong cost/quality point for the constraints |
| `text-embedding-ada-002` (1536d) | Battle-tested, well-known | Older, deprecated, similar shape to 3-small | Rejected — no advantage over 3-small |
| BGE / E5 / GTE open-weights (varied dims) | Self-hosted, no vendor cost | Requires inference infra (GPU or slow CPU); operational burden | Rejected — too much infra for hobby project |
| `nomic-embed-text` (768d) via Ollama | Free, local, no API calls | Lower quality on retrieval benchmarks | Kept as offline-experiment alternative, not primary |
| **Mix dimensions in one collection** with version tags | "Flexible" | Silent corruption door, no failure mode that's actually safe | **Hard rejected** — this is the failure pattern MTC-01 exists to prevent |
| Runtime embedder dispatch by query class | Hyper-tuned | Adds enormous complexity for marginal gain; impossible to A/B test | Rejected — premature optimization |

## References

- [BRD-01 §3.7 MTC-01](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — one collection per embedding model
- [BRD-01 §3.7 MTC-11](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — text-embedding-3-small lock
- [BRD-01 §7.2 BRD.01.3206](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — AI/ML topic
- `apps/api/src/config.py.embedding_dimension` — first guardrail
- `apps/api/src/llm/openai.py.OpenAIEmbedder.__init__` — second guardrail
- `apps/api/src/ingestion/pipeline.py.ingest_document` — third guardrail (runtime assert)
- ADR-0002 — Qdrant collection scheme
- ADR-0006 — Embedder Protocol
