---
description: Draft a new MADR-format ADR via the adr-writer subagent. Picks the next sequential number and links to the relevant BRD-01 §7.2 topic if applicable.
argument-hint: [one-line decision summary]
allowed-tools: Read, Glob, Write
---

Delegate this to the `adr-writer` subagent.

Decision summary: $ARGUMENTS

If $ARGUMENTS is empty, fail with: "Provide a one-line decision summary, e.g. `/adr Use Qdrant Cloud free tier instead of pgvector for hybrid search learning goals`".

The subagent will:
1. Find the next ID under `docs/adr/` (creating the dir if needed; first ADR is the meta ADR)
2. Map the decision to one of the 7 ADR topic categories in BRD-01 §7.2 if applicable
3. Draft Context / Decision / Rationale / Consequences / Alternatives Considered
4. Reference the BRD topic explicitly

After the draft, the user reviews and either accepts or asks for revisions.
