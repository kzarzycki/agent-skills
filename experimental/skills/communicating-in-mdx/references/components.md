# Component registry

The authoritative list of components registered globally in the runner. Use the
tag directly in any `.mdx` — **no imports**. Signatures match
`runner/src/components/`.

Prose-first rule: these enhance prose, they don't replace it. Keep Markdown
headings, paragraphs, and lists doing the heavy lifting.

---

## `<Callout tone title>`

Flag a decision, warning, or note. `tone`: `info` (default) · `decision` ·
`warn` · `danger`. `title` optional.

```mdx
<Callout tone="decision" title="Runner model">
We render MDX with a local Vite process. The `.mdx` stays the artifact.
</Callout>
```

## `<Steps>` / `<Timeline>`

Ordered, numbered steps for a phased plan. Children are `<li>` (write them as a
Markdown list inside, or explicit `<li>`). `Timeline` is an alias.

```mdx
<Steps>
- Scaffold the runner
- Build the component library
- Write the skill docs
</Steps>
```

## `<Diff code>`

Before/after code. Lines starting with `+`/`-` are tinted add/remove; others are
context. Pass the raw diff text as `code`.

```mdx
<Diff code={`+ const runner = startVite()
- const runner = uploadToCloud()
  return runner`} />
```

## `<AnnotatedCode code lang notes>`

Syntax-highlighted code (Shiki) with margin notes. `lang` default `ts`. `notes`
is `{ line, text }[]`.

```mdx
<AnnotatedCode lang="ts" code={`export function loadDocs() {
  return import.meta.glob("../.docs/**/*.mdx");
}`} notes={[{ line: 2, text: "Glob resolves through the .docs symlink." }]} />
```

## `<FileTree tree>`

Preformatted directory tree. Pass `tree` as a string, or children.

```mdx
<FileTree tree={`runner/
  src/components/
  bin/mdx-runner.mjs`} />
```

## `<Mermaid chart>`

Mermaid diagram (architecture, flow, sequence). Pass the diagram as `chart` or
as the child string.

```mdx
<Mermaid chart={`graph LR
  MDX[spec.mdx] --> Vite[local Vite] --> Browser`} />
```

## `<Diagram nodes edges height>`

Interactive node-graph: nodes highlight on hover, a tooltip follows the cursor,
and connected edges light up. Use when a diagram benefits from interaction that
a static `<Mermaid>` can't give. `nodes` is
`{ id, x, y, w?, h?, label, tip? }[]` (positions in px from the top-left).
`edges` is `{ from, to, label? }[]` referencing node ids. `height` optional px.

```mdx
<Diagram height={220} nodes={[
  { id: "a", x: 20,  y: 80, label: "spec.mdx", tip: "The artifact — git-diffable." },
  { id: "b", x: 200, y: 80, label: "Vite runner", tip: "Local. Zero network." },
  { id: "c", x: 380, y: 80, label: "browser", tip: "Interactive, hot-reloading." }
]} edges={[{ from: "a", to: "b" }, { from: "b", to: "c" }]} />
```

## `<Columns>`

Side-by-side comparison. Each direct child becomes a column.

```mdx
<Columns>
<div>**MDX** — lighter authoring, needs a runner.</div>
<div>**HTML** — zero deps, heavier to write.</div>
</Columns>
```

## `<Tabs labels>` / `<Collapse summary open>`

`Tabs`: `labels` is `string[]`; each child is the panel for the matching label.
`Collapse`: a `<details>` with `summary`; `open` to start expanded.

```mdx
<Tabs labels={["Before", "After"]}>
<div>The old flow.</div>
<div>The new flow.</div>
</Tabs>

<Collapse summary="Why not single-file HTML?">
Because MDX is the artifact; HTML would be a redundant frozen copy.
</Collapse>
```

## `<Checklist items>`

Acceptance criteria / task list. Pass `items` as `string[]`, or children `<li>`.

```mdx
<Checklist items={["Renders with zero network calls", "Degrades to Markdown"]} />
```

## `<MetricCard label value delta tone>`

A recap KPI. `tone`: `info` · `ok` · `warn` · `danger` (colors the delta).

```mdx
<MetricCard label="Tokens vs HTML" value="-40%" delta="lighter" tone="ok" />
```

## `<QuestionForm questions>`

Interview form. `questions` is `{ id, label, type?, options? }[]` where `type`
is `text` (default) or `choice` (needs `options: string[]`). The user fills it,
clicks **Copy answers**, and pastes an `ANSWERS<<< … >>>ANSWERS` token back into
chat for you to parse.

```mdx
<QuestionForm questions={[
  { id: "scope", label: "v1 scope", type: "choice", options: ["docs only", "docs + canvas"] },
  { id: "notes", label: "Anything else?" }
]} />
```

Wireframe canvas components are documented separately in `wireframe.md`.
