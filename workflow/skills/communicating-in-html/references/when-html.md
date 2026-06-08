# When HTML beats Markdown — the decision doctrine

The deep-dive behind the brief version in `../SKILL.md`. Before producing a
deliverable, decide the *channel*, not just the content.

## The thesis (why this skill exists)

Markdown became the default way agents talk to humans — but as agents produce
richer, longer, more structural output, Markdown's flatness becomes a tax: no
real columns, no spatial layout, no interaction, no color/hierarchy, and a
file you can't actually read past ~100 lines. The argument (Thariq Shihipar,
Claude Code lead, *"The Unreasonable Effectiveness of HTML,"* May 2026) is that
HTML is the better channel for plans, comparisons, mockups, reviews, and
reports — a single self-contained file the user can read, share, and interact
with. This skill operationalizes that for three concrete jobs: **reporting**,
**interviewing**, and **offering choices**.

Source: https://claude.com/blog/using-claude-code-the-unreasonable-effectiveness-of-html ·
examples: https://thariqs.github.io/html-effectiveness/

## The recognition heuristic

**Reach for HTML when the content has any of:**

- **Comparison** — two+ things side by side (options, before/after, A/B/C).
- **Spatial information** — layout, position, timeline, flow, hierarchy that
  Markdown can only stack vertically.
- **Interaction** — the user will *do* something: pick, fill in, adjust a
  slider, toggle, annotate, edit.
- **Reference material** — something the user will return to, navigate, or
  share, not read once and discard.
- **Meaningful color / diagrams / charts** — status, encoding, SVG, where color
  carries information.
- **A one-off editor** — a tailored little interface for a specific task.
- **Length** — it would exceed ~100 lines of Markdown, i.e. become a wall.

**Stay in Markdown / plain chat when:**

- It's a short conversational reply or a genuine few-sentence answer.
- It's code-only output, or a terminal-style answer.
- It's a disposable summary the user won't act on.
- It needs clean version-control diffs (HTML diffs poorly).

When in doubt: *if the user is going to **do** something with it — share it,
decide from it, fill it in — make it HTML. If they'll just read a line and move
on, keep it Markdown.*

## The cost to weigh

HTML runs ~2-4× the tokens of the Markdown equivalent and takes longer to
generate. That's the whole reason for the carve-outs above — reserve HTML for
deliverables where layout, shareability, interaction, or navigation genuinely
earns the cost. Don't gold-plate a throwaway.

## Universal requirements (every artifact this skill emits)

1. **One self-contained file** — CSS and JS inlined, no build step, no external
   fonts. (CDN only when interactivity demands it, and say so.)
2. **Works offline** — no required network calls; opens by double-click.
3. **Mobile responsive** — viewport meta, readable at 360px.
4. **Genuinely laid out** — columns for comparisons, timelines for sequences;
   not Markdown-style vertical stacking wearing a `<div>`.
5. **Self-explanatory in 5 seconds** — title + one framing sentence up top.
6. **Tasteful and restrained** — readable type, calm color, real hierarchy.
7. **Export where it's an editor/form** — the user can get their data back out
   (this skill uses the copy-paste-back token; see `../assets/copy-back.js`).

## Output + delivery

- Save as `kebab-case.html` next to the work (or in `.work/` if the workflow
  plugin's workspace exists).
- Surface it to the user (e.g. `SendUserFile` on Claude Code web/mobile) or
  print the absolute path and offer to open it.
- Always leave a 3-5 bullet TL;DR in chat too — the file is the artifact, the
  chat keeps the headline.

## Prior art (credit + alternatives)

This doctrine is a clean-room synthesis of Thariq's thesis. Two installable
skills cover overlapping ground and are worth knowing:

- **`dogum/html-artifacts`** (Apache-2.0) — a direct operationalization of the
  same post, with per-category reference patterns. Closest match for the
  reporting case; tiny repo, readable end to end.
- **`careerhackeralex/visualize`** (MIT) — strong, well-maintained report/slide/
  dashboard generator (10 formats, Chart.js, PNG/PDF export). If you want a
  drop-in for *reports* specifically, install it:
  `claude plugin marketplace add careerhackeralex/visualize`.

This skill's distinct value is bundling all three channels — **reporting**,
**interviewing** (a form whose answers come back), and **offering options** (a
pickable mockup gallery) — as one optional, zero-coupling enrichment over a
single shared design system.
