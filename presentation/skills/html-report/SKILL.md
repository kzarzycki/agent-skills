---
name: html-report
description: >
  Deliver a report as a single self-contained HTML file instead of a Markdown
  chat dump — visualized concepts, KPI cards, tables, inline charts, callouts,
  and a clean reading layout. Use when the user asks for a report, summary,
  analysis, audit, dashboard, findings, scorecard, or "write this up nicely",
  and a browser page reads better than chat Markdown. Trigger on "make me a
  report", "write up the findings", "build a dashboard", "summarize this
  visually", "as an HTML report", "nice report", "executive summary",
  "scorecard", or any request where structure, tables, and visuals matter more
  than a wall of text. The output is one .html file with everything inlined
  (no build, no CDN, no server) that the user opens in a browser.
---

# HTML Report — browser-grade write-ups instead of Markdown

Produce a single self-contained `.html` file that communicates findings the way
a designer would: a clear hierarchy, KPI cards, real tables, inline SVG charts,
and callouts — not a long Markdown message the user has to scroll.

## Channel check first

Read `../../references/when-html.md` — the shared "HTML vs Markdown" doctrine
(after Thariq Shihipar's *Unreasonable Effectiveness of HTML*). Build a page
only when the content earns it: comparison, layout, reference material, color/
charts, or it would be a >100-line Markdown wall. A few-sentence answer stays
in chat.

## When to fire

The user wants a **report, summary, analysis, audit, dashboard, or scorecard**
and the content is structural (numbers, comparisons, sections, status) rather
than a one-line answer. If the answer fits in a sentence, just say it — don't
build a page. If it has sections, metrics, or a table, build the page.

Sibling skills: **html-interview** (collect input via a form), **html-options**
(present choices/mockups to pick from). All three share `../../assets/design-system.css`.

## The delivery contract (read this first)

1. **One file, everything inlined.** Inline `assets/design-system.css` inside a
   `<style>` tag and any chart SVG/JS directly. No external fonts, no CDN, no
   build step. It must open offline by double-click.
2. **Write it to a predictable path**, e.g. `./<slug>-report.html` (or `.work/`
   if the workflow plugin's workspace exists).
3. **Surface it to the user.** Use the harness's file-surfacing affordance
   (e.g. `SendUserFile` on Claude Code web/mobile) so it lands as an openable
   artifact; otherwise print the absolute path and tell them to open it.
4. **Echo a 3-5 bullet TL;DR in chat** too. The HTML is the artifact; the chat
   still gets the headline so the user doesn't have to open it to get the gist.

## Build steps

1. **Start from `../../assets/base-template.html`.** Fill `{{TITLE}}`,
   `{{EYEBROW}}`, `{{SUBTITLE}}`, `{{FOOTER}}` (date + source).
2. **Inline the stylesheet.** Paste the entire contents of
   `../../assets/design-system.css` into the `<style>` block. Override
   `--accent` if the user has a brand color.
3. **Choose a format** by the shape of the content (see Format selection).
4. **Lay out content** using the component vocabulary in
   `references/components.md` — KPI grid, cards, tables, callouts, inline bars.
5. **Charts:** prefer hand-written **inline SVG** for bars/lines/donuts (see
   `references/charts.md`) — zero dependencies. Only reach for a CDN charting
   lib if the user explicitly needs interactivity, and say so.
6. **Validate:** the file opens with no console errors, no network requests,
   readable at 360px wide and on desktop. Check both `data-theme="dark"` and
   `light` if the user cares about print.

## Format selection

| Content shape | Format | Notes |
|---|---|---|
| Narrative with sections, some metrics | **Long-page** | Default. `h2` sections, callouts, tables. |
| Status snapshot, many metrics | **Dashboard** | KPI grid up top, supporting cards/tables below. |
| Step-by-step or pitch | **Slideshow** | Full-viewport sections + keyboard nav. See `references/charts.md`. |
| Single big idea, few numbers | **Infographic** | One vertical flow, oversized numbers, minimal text. |

Don't overbuild. Long-page is right ~70% of the time.

## Quality bar

- Every number a reader might question has a **source or as-of date** nearby.
- Tables right-align numerics (`td.num`) and use tabular figures.
- No lorem, no placeholder charts — if you don't have the data, omit the chart.
- Color carries meaning consistently (ok/warn/danger), never decoration.
- Headline answer is visible **above the fold** without scrolling.

## Anti-patterns

- Reaching for a charting CDN when inline SVG would do (breaks offline).
- Pasting a giant Markdown report into chat *and* building HTML — pick HTML, keep chat to the TL;DR.
- Multi-file output (separate .css/.js) — it won't travel; inline everything.
- Decorative charts that encode no real data.
- Building a page for a one-sentence answer.
