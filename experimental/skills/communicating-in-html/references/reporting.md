# Playbook — reporting in HTML

Deliver findings as a single self-contained `.html` the way a designer would:
clear hierarchy, KPI cards, real tables, inline-SVG charts, callouts — not a
long Markdown message the user scrolls.

## Channel check

Build a page only when the content is structural (sections, metrics, a table,
comparisons, status). A one-sentence answer stays in chat. See the use/stay
lists in `../SKILL.md` and the full rationale in `when-html.md`.

## Build steps

1. Start from `../assets/base-template.html`. Fill title / eyebrow / subtitle /
   footer (date + source).
2. Inline the entire `../assets/design-system.css` into the `<style>` block.
   Override `--accent` for a brand color.
3. Pick a format (below) by the shape of the content.
4. Lay out with the component vocabulary in `components.md` — KPI grid, cards,
   tables, callouts, inline bars.
5. Charts: prefer hand-written **inline SVG** (`charts.md`) — zero deps, offline.
   Reach for a CDN charting lib only if the user needs interactivity, and say so.
6. Validate: opens with no console errors, no network requests, readable at
   360px and on desktop.

## Format selection

| Content shape | Format | Notes |
|---|---|---|
| Narrative with sections, some metrics | **Long-page** | Default (~70% of cases). `h2` sections, callouts, tables. |
| Status snapshot, many metrics | **Dashboard** | KPI grid up top, supporting cards/tables below. |
| Step-by-step or pitch | **Slideshow** | Full-viewport sections + keyboard nav (`charts.md`). |
| Single big idea, few numbers | **Infographic** | One vertical flow, oversized numbers, minimal text. |

## Quality bar

- Every questionable number has a **source or as-of date** nearby.
- Numerics right-aligned (`td.num`), tabular figures.
- No lorem, no placeholder charts — omit a chart you don't have data for.
- Color carries meaning consistently (ok/warn/danger), never decoration.
- The headline answer is visible **above the fold**.
- Echo a 3-5 bullet TL;DR in chat alongside the file.
