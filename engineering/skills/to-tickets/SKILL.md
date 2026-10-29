---
name: to-tickets
description: Break a plan, spec, or the current conversation into tracer-bullet tickets that declare their blocking edges, and write them as a split manifest file. Writes no tracker state.
disable-model-invocation: true
---

# To Tickets

Break a plan, spec, or conversation into **tickets**: tracer-bullet vertical slices, each naming the tickets that **block** it.

The output is a **split manifest** file; creating issues from it is the caller's step, so a flow engine or a lead can apply it its own way. Never create, edit or close an issue, and never touch a parent issue. If the user wants the tickets on the tracker, point to the realization file `docs/agents/issue-tracker.md` names (for GitHub, the `github-tracker` skill's `github.md`, Publish an issue batch), which takes the manifest as its input.

## Draft

Work from the conversation. If the user passes a reference (spec path, issue number or URL), read its full body and comments. Explore the code as far as the slicing needs, use the `GLOSSARY.md` vocabulary, and respect the ADRs in the area. Look for prefactoring that makes the change easy; it goes first.

- Each slice cuts a narrow but complete path through every layer (schema, API, UI, tests), never one layer on its own.
- A finished slice is demoable or verifiable on its own.
- Each slice fits one fresh context window.
- A ticket's blockers are only the tickets that genuinely gate it; a ticket with none can start immediately.

A **wide refactor** is the exception: one mechanical change (rename a column, retype a shared symbol) whose blast radius breaks call sites across the codebase at once, so no vertical slice lands green. Sequence it expand–contract:

1. An expand ticket adds the new form beside the old.
2. Migrate tickets, each blocked by the expand and sized by blast radius (per package or directory), move the call sites over while the old form keeps CI green.
3. A contract ticket, blocked by every migrate ticket, deletes the old form.

If even the migrate batches can't stay green alone, they share an integration branch and all block a final integrate-and-verify ticket, the only one that promises green.

## Approve

Present the breakdown as a numbered list: title, blocked by, and the end-to-end behaviour each ticket delivers. Ask whether the granularity is right, whether each edge is a real gate, and what to merge or split. Iterate until the user approves.

## Write the manifest

Write the approved tickets as one JSON file, `.scratch/<feature-slug>/split-manifest.json` unless the caller names a path:

```json
{
  "version": 1,
  "items": [
    {"title": "Expose account status", "spec": "<the ticket body>", "blocked_by": []},
    {"title": "Render account status", "spec": "<the ticket body>", "blocked_by": ["Expose account status"]}
  ]
}
```

- `title` is the ticket's identity and is unique in the file; `blocked_by` lists the titles of its blockers, none for a ticket that can start immediately. Blockers form no cycle and name no ticket outside the file.
- `spec` is the ticket body in the issue template below, so the tracker step posts it unchanged. Its "Blocked by" section lists the same tickets by title.
- The manifest has no labels and no parent: the caller adds those, since they depend on the tracker and the project's label map.
- List tickets in dependency order (blockers first). Leave file paths and code snippets out of specs; they go stale. The exception is a prototype snippet (state machine, reducer, schema, type shape) that states a decision more precisely than prose: inline only its decision-rich part and say it came from a prototype.

Report the manifest's path and stop.

<issue-template>

## What to build

The end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Blocked by

- A reference to each blocking ticket, or "None (can start immediately)".

</issue-template>
