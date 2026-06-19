# communicating-in-mdx — design

**Date:** 2026-06-19
**Status:** Approved, ready for implementation plan

## Purpose

A skill that teaches Claude to write specs, plans, designs, and recaps in MDX, rendered by a fully local runner. It is an orthogonal enrichment layer — loaded alongside superpowers, it makes Claude prefer MDX for rich documents Claude and the user iterate on. Unloaded, nothing changes.

It is the MDX counterpart to the existing `communicating-in-html` skill. The two coexist (see Coexistence). MDX becomes the default for rich docs only if its output quality earns it.

Inspired by BuilderIO's `visual-plan`/`visual-recap`, but with one hard difference: **no remote services.** visual-plan's renderer is closed and hosted at `plan.agent-native.com` and uploads plan content by default. This skill ships its own local renderer; nothing leaves the machine unless the user sends the `.mdx` themselves.

## Goals

- Lighter authoring: write Markdown prose and drop in components, instead of hand-writing div+CSS.
- A reusable, registered component library so every document shares one visual language.
- Real interactivity (live React components).
- The `.mdx` source as the portable, git-diffable, hand-editable artifact.
- Fully local rendering — no telemetry, no upload, no hosted viewer.

## Non-goals (v1)

- Single-file HTML export, PDF/PNG export.
- Multi-document cross-linking or navigation site.
- Auth, sharing infrastructure, or a GitHub Action recap automation.
- Replacing `communicating-in-html`.

## Architecture — MDX is the artifact, rendering is a local function

```
spec.mdx   (artifact: git-diffable, hand-editable, shareable, degrades to Markdown)
   │
   ▼   local Vite dev process, run in tmux
localhost:5173   →   rendered, interactive, hot-reloading
```

The unit of exchange is the `.mdx` file. Rendering is a function anyone with the runner applies locally. HTML is never a deliverable — it is only what the browser transiently shows. This dissolves the "self-contained file" concern that anchors the HTML skill: the user shares MDX, and MDX is durable and re-renderable on its own.

**Degrades to Markdown.** A `.mdx` opened with no runner (GitHub, any editor) still reads as Markdown prose; only component tags appear as inert text. This is a designed property, enforced by the prose-first principle below.

## The runner

A Vite + React app **bundled inside the skill** (`runner/`), installed once with `npm install` in the skill directory. It is pointed at whatever project Claude is working in:

```
node runner --dir <project>/.work --open
```

- Serves every `.mdx` in the target directory with an index page, renders the selected one, hot-reloads on edit.
- Claude runs it in a tmux window (`mdx-runner`) and starts/stops/restarts it autonomously — same operational pattern as the powerpoint-mcp dev server.
- Documents are written into the current project (`.work/` if it exists, else `docs/`), never into the skill. The runner lives in the skill; content lives with the user's work.

One bundled runner serves many document directories. The rejected alternative — scaffolding a runner copy into each repo — pollutes every project with `node_modules`.

## Component library

Components are **registered globally** via MDXProvider (`providerImportSource`), so `.mdx` files need no imports — the author writes the tag directly. The authoritative tag list lives in `references/components.md`; Claude authors from the registry, never from memorized tags.

**Document set:**

| Component | Used for |
|---|---|
| `<Callout tone>` (decision / warn / info) | flagging choices and risks |
| `<Steps>` / `<Timeline>` | phased plans |
| `<Diff>` | before/after code |
| `<AnnotatedCode>` | code with margin notes anchored to lines |
| `<FileTree>` | structure |
| `<Mermaid>` | architecture, flow, sequence diagrams |
| `<Columns>` | side-by-side comparison |
| `<Tabs>` / `<Collapse>` | progressive disclosure |
| `<Checklist>` | acceptance criteria, task lists |
| `<MetricCard>` | recap KPIs and results |
| `<QuestionForm>` | interviewing (see Interactivity) |

**Wireframe canvas:** `<Canvas>` holds spatial `<Screen>` artboards built from low-fidelity primitives (`<WBox>`, `<WText>`, `<WButton>`, `<WInput>`, and similar), styled by shared `--wf-*` design tokens, with annotation pins anchored to elements. Deliberately low-fidelity — wireframe altitude, not pixel-perfect, which is the right level for communicating a design.

## Authoring principles (encoded as skill rules)

- **Prose-first, components-as-enhancement.** The raw `.mdx` must still read as Markdown when unrendered. A document that is mostly component tags is an anti-pattern.
- **No imports in documents.** Global registration is what delivers the lighter-authoring payoff.
- **Author from the registry**, not from memory.

## Interactivity and answers back

`<QuestionForm>` reuses the HTML skill's copy-back token, adapted to React. The user fills the form in-browser; it serializes answers into an `ANSWERS<<< … >>>ANSWERS` token the user pastes into chat, which Claude parses. The interview loop works with no backend.

## Coexistence with communicating-in-html

Both are enrichment layers; Claude picks per context.

- **MDX** — rich documents Claude and the user iterate on; anything using the component vocabulary or live interactivity; Node is available.
- **HTML** — zero-dependency one-offs; a file for someone who will not run a runner.

HTML's one irreplaceable virtue is zero dependencies: it renders on any machine with a browser, for anyone. MDX always needs the runner. That is why HTML stays as the fallback.

## Skill structure

```
experimental/skills/communicating-in-mdx/
  SKILL.md                  # when-MDX, the registry, principles, runner usage
  references/
    components.md           # full tag reference, props, examples
    wireframe.md            # canvas system and tokens
    when-mdx.md             # MDX vs HTML vs Markdown decision doctrine
    runner.md               # lifecycle, tmux, --dir, troubleshooting
  runner/                   # bundled Vite app
    package.json            # pinned deps
    src/components/*        # component library, one file each
    src/App.tsx
    index.html
    vite.config.ts
  assets/
    starter.mdx             # exemplar document
```

## Tech stack (pinned)

Vite · React · `@mdx-js/rollup` (with `providerImportSource` for global components) · `mermaid` · `shiki` (syntax highlighting). Dev-server only in v1 — no `vite build` / single-file export, since MDX is the artifact.

## Defaults

- Document directory: `.work/` if present, else `docs/`.
- React, not Preact — best MDX ecosystem and types; bundle weight is irrelevant since the bundle is never shared.
- Shiki over Prism for highlighting.
- Runner port 5173.

## Success criteria

- Claude can write a spec/plan/recap in MDX and view it rendered via the local runner with zero network calls.
- A shared `.mdx` renders for any second machine that runs the bundled runner, and still reads as Markdown without it.
- Authoring a rich document costs materially fewer tokens than the hand-written HTML equivalent.
- Output quality is good enough that the user considers making MDX the default for rich documents.
