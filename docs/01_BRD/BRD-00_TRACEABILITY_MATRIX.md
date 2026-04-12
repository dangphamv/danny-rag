# BRD-00: Traceability Matrix

> Format adapted from `.agents/skills/doc-brd/SKILL.md` §Step 10. The upstream `ai_dev_ssd_flow/01_BRD/BRD-00_TRACEABILITY_MATRIX-TEMPLATE.md` is not vendored in this project.

## BRD Index

| BRD ID | Title | Type | Status | Version | Owner | Upstream Sources | Downstream Artifacts |
|---|---|---|---|---|---|---|---|
| [BRD-01](./BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) | RAG Knowledge Chatbot Platform | Platform | Draft | 1.1 | Danny Pham | `../plan.md` (`upstream_mode: none`) | (none yet — PRD-01 pending) |

## Cross-BRD Dependencies

None. BRD-01 is the first and only BRD in this project.

## Maintenance Notes

- Update this matrix in the same commit as any BRD change.
- Add a new row when a new BRD is created.
- Update the **Downstream Artifacts** column when PRD/EARS/BDD/ADR documents are created and they tag this BRD via `@brd: BRD.01.xxxx`.
- Cross-BRD dependencies (`@depends: BRD-NN`) belong in the section above.
