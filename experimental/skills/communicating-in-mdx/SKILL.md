---
name: communicating-in-mdx
description: >
  Optional enrichment layer. When loaded, the agent writes specs, plans,
  designs, recaps, and reports as MDX — Markdown prose plus a registered
  component library — rendered by a fully local Vite runner the agent runs
  itself. No remote services: the .mdx is the artifact (git-diffable,
  hand-editable, shareable, degrades to plain Markdown), and rendering is a
  local function. Orthogonal and zero-coupling: other skills keep working in
  plain Markdown when this isn't loaded. Fires when you are about to write a
  spec / plan / design / recap / report / dashboard the user will read,
  iterate on, or decide from — and prose-only Markdown would lose layout,
  comparison, diagrams, wireframes, or interaction. Coexists with
  communicating-in-html (use HTML for zero-dependency one-off files; use MDX
  for rich documents you and the user iterate on where Node is available).
---

# Communicating in MDX

An orthogonal enrichment layer — like a writing style, not a task. When this
skill is loaded, prefer **MDX over plain Markdown** for documents the user will
read, iterate on, or decide from: specs, plans, designs, recaps, reports. The
`.mdx` is the artifact; a local runner renders it. Nothing leaves the machine.

It couples to nothing: it triggers on the *activity*, so whatever else you're
doing (planning, designing, recapping) simply renders in MDX when that lands
harder. Unloaded, nothing changes.

## When MDX beats plain Markdown (and when it doesn't)

**Reach for MDX when the content has any of:** comparison (things side by side)
· a plan with phased steps · architecture / flow / sequence that wants a
diagram · code with margin notes or before/after · a UI idea that wants a
wireframe · a recap with metrics · an intake form whose answers come back · or
it would otherwise be a wall of flat Markdown.

**Stay in plain Markdown / chat when:** it's a short reply · code-only or
terminal output · a disposable summary · or Node/the runner isn't available.

Full doctrine, and MDX-vs-HTML-vs-Markdown: `references/when-mdx.md`.

## The core discipline

1. **Prose-first, components-as-enhancement.** Write real Markdown prose; drop
   in components only where they earn it. The raw `.mdx` must still read as
   Markdown when nobody renders it. A document that is mostly component tags is
   an anti-pattern.
2. **No imports in documents.** Components are registered globally — write the
   tag (`<Callout>`, `<Mermaid>`) directly, never `import` anything in a `.mdx`.
3. **Author from the registry, not from memory.** Before using components, read
   `references/components.md` (and `references/wireframe.md` for the canvas).
   It is the authoritative tag list and signatures.

## The component vocabulary

Document components (full props + examples in `references/components.md`):

| Tag | For |
|---|---|
| `<Callout tone>` | decisions, warnings, notes |
| `<Steps>` / `<Timeline>` | phased plans |
| `<Diff>` | before/after code |
| `<AnnotatedCode>` | code with margin notes |
| `<FileTree>` | structure |
| `<Mermaid>` | architecture, flow, sequence |
| `<Columns>` | side-by-side comparison |
| `<Tabs>` / `<Collapse>` | progressive disclosure |
| `<Checklist>` | acceptance criteria, task lists |
| `<MetricCard>` | recap KPIs and results |
| `<QuestionForm>` | interviewing — answers POST back to the runner (token fallback) |
| `<OptionGallery>` / `<Option>` | offer visual mockups to pick from; pick streams back |

Wireframe canvas for UI/design docs — `<Canvas>`, `<Screen>`, and low-fi
primitives (`<WBox>` `<WText>` `<WButton>` `<WInput>` `<WImage>` `<WRow>`
`<WCol>`): see `references/wireframe.md`.

## Start from a template

Don't author from a blank file. `assets/templates/` holds three worked
starting points — copy one into the project's `.work/`, rename it, and replace
the example content:

| Template | Activity | Shows off |
|---|---|---|
| `interview.mdx` | intake / brainstorm | `<QuestionForm>` with answer streaming |
| `change-spec.mdx` | spec / plan | `<Diagram>` (hover tips + edge highlight), `<Diff>`, `<Steps>`, `<Collapse>` |
| `pick-a-look.mdx` | offer options | `<OptionGallery>` of wireframe mockups |

`assets/starter.mdx` is a broader showcase of the whole component set. These are
inspiration, not contracts — keep the structure that fits, drop the rest.

## Using this from brainstorming, writing-plans, and other workflows

This skill is the *medium*; another skill is usually driving the *activity*.
When a workflow asks for a spec, plan, design, recap, or intake — and the user
wants it rich — render it as MDX instead of flat Markdown:

1. Copy the matching template from `assets/templates/` into the project's
   `.work/` (e.g. brainstorming intake → `interview.mdx`; a writing-plans plan
   or a design → `change-spec.mdx`; a layout choice → `pick-a-look.mdx`).
2. Write the real content into it, prose-first.
3. **Serve it** with the runner (below) and give the user the URL — that is the
   review surface. For brainstorming/option questions, the form or gallery
   streams answers back; you don't block on copy-paste.

The workflow's own discipline still applies (brainstorming asks one question at
a time; writing-plans keeps tasks bite-sized) — MDX only changes how the
artifact is rendered, not how the workflow is run.

## Rendering — run the local runner

The runner is a Vite + React app bundled in this skill at `runner/`. Install
once: `cd runner && npm install`.

Render a project's docs:

```bash
node <skill>/runner/bin/mdx-runner.mjs --dir <project>/.work --open
```

Start it as a background process and start/stop/restart it autonomously — no
tmux required (the agent's shell can launch a detached process directly; tmux is
optional if the user wants a window to attach to). It serves every `.mdx` in
`--dir` at `http://localhost:5173` with a sidebar index and hot reload. Flags
and troubleshooting: `references/runner.md`.

## Delivery + getting answers back

- Write `kebab-case.mdx` into the project's `.work/` (or `docs/` if no `.work/`).
  That directory is what the runner serves.
- **The artifact is the `.mdx`** — it is what you share, commit, and reopen. The
  rendered page is transient. Never produce HTML as a deliverable.
- **Always leave a 3-5 bullet TL;DR in chat too** — the file is the artifact,
  the chat keeps the headline.
- `<QuestionForm>` answers POST back to the runner's own `/__mdx/answers`
  endpoint (same-origin localhost — nothing leaves the machine) and land in
  `runner/.answers.jsonl`. Watch that file (a backgrounded watcher that wakes
  you on a new line) to pick them up with no copy-paste. Offline fallback: a
  pasteable `ANSWERS<<< … >>>ANSWERS` token.

## Coexistence with communicating-in-html

Both are enrichment layers; pick per context.

- **MDX** — rich documents you and the user iterate on; anything using the
  component vocabulary or a wireframe; Node and the runner are available.
- **HTML** — zero-dependency one-offs; a single file for someone who will not
  run a runner. HTML's one irreplaceable virtue is that it needs no toolchain.

## Anti-patterns

- A `.mdx` that's 90% component tags — it stops reading as Markdown unrendered.
- `import`ing anything inside a `.mdx` document.
- Producing an HTML file as the deliverable (the MDX is the deliverable).
- Reaching for MDX in a plain terminal with no Node — degrade to Markdown.
- Using components you didn't confirm against `references/components.md`.
