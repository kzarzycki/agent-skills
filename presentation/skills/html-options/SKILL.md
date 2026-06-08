---
name: html-options
description: >
  Present options, mockups, or design directions as nicely displayed visual
  cards the user can compare side by side and pick from — instead of a bulleted
  Markdown list. Two channels: (a) the native AskUserQuestion HTML preview for
  in-chat pick-one/pick-few decisions with a small styled preview per option;
  (b) a standalone self-contained HTML option gallery when the choices are rich
  mockups (layouts, color schemes, page designs) that deserve real side-by-side
  rendering, with a copy-paste-back selection token. Use when offering the user
  a choice between approaches, designs, layouts, copy variants, plans, or color
  schemes. Trigger on "show me options", "give me a few directions", "mockups to
  choose from", "which layout", "design options", "pick a style", "A/B/C
  variants", "let me choose", or any moment you'd otherwise list choices as
  plain text but a visual comparison would help the user decide.
---

# HTML Options — choices and mockups the user can see and pick

When you offer the user a choice, a Markdown bullet list makes them imagine each
option. Rendering the options — even tiny previews — lets them *see and compare*,
and pick faster and better. This skill covers both the lightweight in-chat path
and the full standalone gallery.

## Channel check first

Read `../../references/when-html.md` — the shared "HTML vs Markdown" doctrine.
Offering choices is the *comparison* case: rendered options the user compares
side by side beat an imagined Markdown list. Below is how to pick the rendering
channel within that.

## Pick the channel first

| Situation | Channel |
|---|---|
| 2-4 options, pick one/few, a small preview helps (layout, color, card style) | **A — AskUserQuestion HTML preview** |
| Rich mockups: full layouts, page designs, multi-element comparisons, >4 options | **B — standalone HTML gallery** |
| Pure text choices, no visual benefit | Plain `AskUserQuestion` (no preview) — don't overbuild |

Sibling skills: **html-interview** (multi-field intake), **html-report** (write-ups).
Shared design system: `../../assets/design-system.css`.

## Channel A — AskUserQuestion with HTML previews

The agent harness can render a small HTML preview per option natively, so the
choice stays *in chat* — no file, no paste-back. Each option's `preview` is a
**styled `<div>` fragment** (the SDK strips `<script>`, `<style>`, and
`<!DOCTYPE>`, so use **inline `style=""` only**).

Use this when the difference between options is visual but compact: a metric
card layout, a color scheme, a button style, a chart type.

Per option provide: a `label`, a one-line `description` (the tradeoff), and a
`preview` div. Keep previews self-contained with inline styles. Example option
preview (compact KPI card):

```html
<div style="padding:12px;border:1px solid #2a3346;border-radius:10px;background:#131722;font-family:sans-serif">
  <div style="font-size:12px;color:#9aa4b2;text-transform:uppercase">Active users</div>
  <div style="font-size:28px;font-weight:700;color:#e6e9ef">1,284</div>
  <div style="font-size:12px;color:#51cf66">▲ 12%</div>
</div>
```

Give 2-4 genuinely distinct options. If they're near-identical, you're not
offering a real choice — collapse them.

## Channel B — standalone HTML option gallery

For real mockups that deserve full rendering, build one self-contained `.html`
showing the options **side by side** as cards, each with a live preview, and let
the user select. Selection returns via the same copy-paste-back token as
html-interview.

Build steps:

1. Start from `references/options-template.html`.
2. Inline `../../assets/design-system.css` and `../../assets/copy-back.js`.
3. One `.option` card per choice in a `.grid cols-2`/`cols-3`. Each card:
   - a **rendered preview** (real HTML/CSS of the mockup, or inline SVG),
   - a title + a sentence on what it optimizes for,
   - a radio (pick one) or checkbox (pick several) to select.
4. `CopyBack.init({ required: ['choice'] })` so the copy button stays disabled
   until something is picked. The token carries the chosen id(s).
5. Surface the file; tell the user to click their pick, hit Copy, paste back.
6. On paste-back, parse the `ANSWERS<<< … >>>ANSWERS` token, **confirm the pick
   in one line**, and proceed.

## Making options good (both channels)

- **Distinct, not shades.** Each option should change the outcome meaningfully.
- **Name the tradeoff** under each, not just a label ("Dense — more on screen,
  busier" vs "Airy — calmer, more scrolling").
- **Show, don't describe.** A rendered preview beats an adjective.
- **Mark your recommendation** if you have one ("Recommended" badge), but still
  let them choose — and always allow an **"Other / none of these"** path.
- **3-ish options.** Two feels thin, five is paralysis.

## Anti-patterns

- A preview that's just the label in a box — render the actual difference.
- `<script>`/`<style>` inside an AskUserQuestion preview (stripped — inline styles only).
- Five barely-different options.
- Building a full gallery for a plain yes/no (use AskUserQuestion).
- No "none of these" escape.
- Not confirming the selection back before acting on it.
