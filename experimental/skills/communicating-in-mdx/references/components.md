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

## `<DocDiff a b labels mode>`

Rendered, section-matched diff of two MDX docs — each side is the real document
(tables, callouts, lists render as themselves), not a text diff. `a`/`b` are doc
**slugs** (filename without `.mdx`) whose source is read from the runner; matched
by H2 heading and marked same / changed / added / removed. Changed sections get
word-level highlighting (green added, red strikethrough removed). `labels` is
`[before, after]` (default `["before","after"]`). `mode` is `auto` (default) ·
`split` (two columns) · `inline` (one unified tracked-changes column); a toolbar
toggle flips it live. **Auto heuristic:** a section with a table → `split`
(aligned cells compare best side-by-side); prose / lists → `inline`. Caveat:
bold/`code` *inside* a diffed run renders as plain text (highlight is on text,
never injected into MDX source, so table pipes / markers never break). Keep diff
source docs as hidden `_`-prefixed slugs so they don't clutter the sidebar.

```mdx
<DocDiff a="_spec-v1" b="_spec-current" labels={["v1 — draft", "v2 — reworked"]} />
```

## `<DocInclude slug>`

Embed another doc's CURRENT content inline, rendered through the full MDX
pipeline. Lets a page show a live artifact without duplicating its text — point
it at a canonical slug that always mirrors the latest version (e.g. a review/gate
page that shows the spec itself, with meta/changelog kept separate below). `slug`
is the doc filename without `.mdx`.

```mdx
<DocInclude slug="_spec-current" />
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

A plain ` ```mermaid ` fenced code block renders as a diagram too — the runner
overrides `pre`, so a mermaid fence becomes a `<Mermaid>` automatically. Prefer
the fence in documents (specs, plans) so the source stays portable Markdown that
GitHub also renders; reach for the `<Mermaid>` tag only when the diagram string
is computed. Fences render inside `<DocInclude>` / `<DocDiff>` as well.

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

## `<QuestionForm questions id>`

Interview form. `questions` is `{ id, label, type?, options? }[]` where `type`
is `text` (default) or `choice` (needs `options: string[]`). Optional `id`
labels the submission (defaults to the document slug).

On **Submit answers** the form POSTs `{ form, answers }` to the runner's own
`/__mdx/answers` endpoint, which appends them to `runner/.answers.jsonl` — the
agent reads that file, so answers come straight back with no copy-paste. This is
same-origin localhost; nothing leaves the machine. If there's no live runner
(e.g. the file was opened statically), it falls back to a copy-paste
`ANSWERS<<< … >>>ANSWERS` token.

To pick up answers, the agent watches `runner/.answers.jsonl` for a new line
(e.g. a backgrounded watcher that wakes it on submit).

```mdx
<QuestionForm id="scope-intake" questions={[
  { id: "scope", label: "v1 scope", type: "choice", options: ["docs only", "docs + canvas"] },
  { id: "notes", label: "Anything else?" }
]} />
```

## `<OptionGallery prompt id>` + `<Option name label>`

Offer visual options to choose from — each `<Option>` holds a real rendered
mockup (wireframes, styled previews, anything). Clicking **Choose this** POSTs
`{ form, choice, label }` to the runner (same channel as `<QuestionForm>`), so
the pick streams straight back. `id` labels the submission. This is the
mockup-picker counterpart to `communicating-in-html`'s "offering options".

```mdx
<OptionGallery id="dashboard-look" prompt="Which dashboard layout do you prefer?">
  <Option name="cards" label="Cards grid">
    <Canvas>
      <Screen name="A" width={220}><WRow><WBox h={40} /><WBox h={40} /></WRow><WBox h={70} /></Screen>
    </Canvas>
  </Option>
  <Option name="list" label="List + detail">
    <Canvas>
      <Screen name="B" width={220}><WRow><WCol><WText lines={4} /></WCol><WBox h={90} /></WRow></Screen>
    </Canvas>
  </Option>
</OptionGallery>
```

Wireframe canvas components are documented separately in `wireframe.md`.
