# When MDX beats Markdown — and how it relates to HTML

The decision doctrine behind the brief version in `../SKILL.md`. Decide the
*channel* before producing the document.

## The thesis

Plain Markdown is the default agent↔human channel, but for rich documents — a
spec, a phased plan, a design with a wireframe, a recap with metrics — its
flatness is a tax: no real columns, no diagrams, no interaction, no wireframes.
MDX keeps Markdown's prose-first authoring and adds a registered component
library, rendered locally. The document stays a `.mdx` file: git-diffable,
hand-editable, and readable as Markdown even with no renderer.

## The recognition heuristic

**Reach for MDX when the content has any of:**

- **Comparison** — options or before/after side by side (`<Columns>`, `<Tabs>`).
- **A phased plan** — ordered steps that read better numbered (`<Steps>`).
- **Architecture / flow** — a diagram says it faster than prose (`<Mermaid>`).
- **Code with explanation** — margin notes or a diff (`<AnnotatedCode>`, `<Diff>`).
- **A UI idea** — a wireframe beats describing a layout (`<Canvas>`).
- **A recap** — metrics and outcomes as cards (`<MetricCard>`).
- **Intake** — structured questions whose answers come back (`<QuestionForm>`).

**Stay in plain Markdown / chat when:**

- It's a short reply or a few-sentence answer.
- It's code-only or terminal output.
- It's a disposable summary the user won't act on.
- Node or the runner isn't available — degrade gracefully.

## MDX vs HTML (the sibling skill)

`communicating-in-html` produces one self-contained `.html` file. The two split
cleanly:

| | MDX | HTML |
|---|---|---|
| Artifact | `.mdx` source | `.html` file |
| Rendering | local Vite runner | opens by double-click |
| Dependencies | Node + runner | none |
| Authoring cost | low (prose + tags) | higher (hand-written CSS) |
| Shareable to a non-runner | reads as Markdown | renders anywhere |
| Iteration | hot reload | re-open file |

**Use MDX** for rich documents you and the user iterate on, where Node is
available. **Use HTML** for a zero-dependency file you hand to someone who won't
run a runner. When in doubt and the toolchain is present, MDX authoring is
lighter and the source is more durable.

## The cost to weigh

MDX needs the runner — a one-time `npm install` and a running Vite process.
That's the whole reason for the carve-outs. Don't stand up a toolchain for a
two-sentence answer.

## The degrade-to-Markdown property

A `.mdx` opened with no runner (GitHub, any editor) still reads as Markdown
prose; only component tags show as inert text. This is why the **prose-first**
rule matters: keep prose carrying the meaning and components enhancing it, and
the raw file stays useful everywhere.
