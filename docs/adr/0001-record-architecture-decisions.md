# 0001. Record architecture decisions

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: N/A (meta-ADR)

## Context

This project is a learning exercise as much as a deployable artifact. Half the value of the work is captured in *why* each tool was picked over its alternatives. Six months from now neither I nor a future collaborator will remember the trade-offs unless they're written down somewhere durable.

Code shows *what* exists. Git history shows *what changed*. Neither answers *why we chose this path over the others we considered*. That's the gap ADRs fill.

## Decision

Use lightweight Markdown ADRs in MADR format (Markdown Architecture Decision Records) under `docs/adr/`. Number sequentially with a 4-digit prefix: `NNNN-kebab-slug.md`. Every architectural commitment gets its own ADR.

Each ADR follows this skeleton:

```markdown
# NNNN. Title

- Status / Date / Deciders / BRD Topic

## Context        — what problem, what forces, what constraints
## Decision       — what we're doing, in 1-2 sentences
## Rationale      — why this choice
## Consequences   — positive / negative / neutral / follow-ups
## Alternatives Considered  — table with pros/cons/why-rejected
## References     — BRD sections, external docs, commits
```

## Rationale

- **In-repo, in version control**: ADRs live next to the code they describe. They get reviewed in PRs and updated alongside refactors.
- **Markdown**: renders everywhere, diffs cleanly, no external tooling.
- **MADR specifically**: lightest-weight ADR convention that still has structure. Heavier conventions (RFC docs, Architecture Documentation specs) bring ceremony this learning project doesn't need.
- **Sequential numbering**: makes the ordering of decisions trivially visible. Status flips (`Superseded by ADR-NNNN`) are easy to express.

## Consequences

### Positive
- Future-me can answer "why Qdrant?" without re-deriving the reasoning from scratch
- New collaborators can read the ADR set and understand the design philosophy in ~30 minutes
- Forces a moment of reflection before committing to any architectural choice ("if I can't write the ADR, the decision isn't ready")

### Negative
- Adds friction to architectural changes — but that friction is the point
- ADRs can rot if they're not maintained alongside refactors

### Neutral / Follow-ups
- The `adr-writer` subagent in `.claude/agents/` automates the file scaffolding
- The `/adr` slash command invokes that subagent
- ADR-required-on-architectural-change is enforced as a hard rule in `CLAUDE.md`

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| No ADRs (rely on git history + comments) | Zero overhead | History rots; comments don't capture rejected alternatives | The whole point of the project is to learn the *why*; not having a `why` artifact defeats it |
| Confluence / Notion | Rich formatting, search | Decoupled from code; goes stale; not version-controlled with the codebase | Solo learning project — wrong tool for the audience |
| RFC docs (à la IETF / Rust RFCs) | Heavy structure, exhaustive | Ceremony overhead too high for a hobby project | Overkill for a 1-developer learning repo |
| Architecture Documentation (arc42, C4 written specs) | Comprehensive system docs | Up-front effort to fill out all sections | The BRD already covers what arc42 would; ADRs cover the decisions arc42 doesn't |

## References

- [MADR — Markdown Architecture Decision Records](https://adr.github.io/madr/)
- [Michael Nygard's original ADR post](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- `.claude/agents/adr-writer.md` — the project's ADR-drafting subagent
- `CLAUDE.md` — "ADR required for any dependency add or architecture change" rule
