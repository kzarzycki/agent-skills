---
name: domain-modeling
description: Build and sharpen a project's domain model, its CONTEXT.md glossary and its ADRs. Use when discussing codebase terminology, writing or editing a CONTEXT.md, or recording or editing an ADR.
---

# Domain Modeling

Sharpen the project's domain language while you design, and write it down as it settles. Reading `CONTEXT.md` for vocabulary needs no skill; this one is for changing the model.

## Where it lives

A single-context repo keeps `CONTEXT.md` at the root and ADRs in `docs/adr/`. A root `CONTEXT-MAP.md` means several contexts: it points to each context's own `CONTEXT.md`, which has a `docs/adr/` beside it for that context's decisions, while the root `docs/adr/` holds system-wide ones. Work in the context the topic belongs to, and ask when that is unclear. Create a file or directory only when you have its first entry to write.

## During the session

- Call out a term that conflicts with `CONTEXT.md` as soon as it is used.
- Propose one canonical word for a vague or overloaded term ("account": the Customer or the User?).
- Probe the boundaries between concepts with concrete edge-case scenarios.
- Check claims about how the system works against the code, and surface contradictions.
- Write each resolved term into `CONTEXT.md` when it settles rather than batching at the end, in the format of [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md). It is a glossary only: no implementation details, spec, or scratch notes.
- Offer an ADR only when the decision is hard to reverse, surprising without context, and the result of a real trade-off; if any of the three is missing, skip it. Format: [ADR-FORMAT.md](./ADR-FORMAT.md).
