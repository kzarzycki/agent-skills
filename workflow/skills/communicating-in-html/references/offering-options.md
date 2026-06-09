# Playbook — offering options / mockups in HTML

When you offer a choice, a Markdown bullet list makes the user *imagine* each
option. Rendering them — even tiny previews — lets them *see and compare*, and
pick faster and better.

## Pick the channel first

| Situation | Channel |
|---|---|
| 2-4 options, pick one/few, a small preview helps (layout, color, card style) | **A — AskUserQuestion HTML preview** |
| Rich mockups: full layouts, page designs, multi-element comparisons, >4 options | **B — standalone HTML gallery** |
| Pure text choices, no visual benefit | Plain `AskUserQuestion` — don't overbuild |

> **Reality check on Channel A.** HTML option previews only render when the
> *host application* opts in via `toolConfig.askUserQuestion.previewFormat:
> "html"` (a custom Agent SDK UI). **Claude Code's own web and desktop clients
> currently drop the `preview` field and show only label + description.** So
> treat the preview as *progressive enhancement*: safe to include, but never
> rely on it carrying the meaning. On Claude Code surfaces, use **Channel B**
> (a gallery file) for genuinely visual choices, or make the label + description
> fully self-sufficient.

## Channel A — AskUserQuestion with HTML previews (SDK hosts that enable it)

Where the host sets `previewFormat: "html"`, each option's `preview` renders as
a small card next to the label — the choice stays *in chat*, no file. The
`preview` is a **styled `<div>` fragment**; the SDK strips `<script>`,
`<style>`, and `<!DOCTYPE>`, so use **inline `style=""` only**. Provide per
option: a `label`, a one-line `description` (the tradeoff), and the `preview`.
Example (compact KPI card):

```html
<div style="padding:12px;border:1px solid #2a3346;border-radius:10px;background:#131722;font-family:sans-serif">
  <div style="font-size:12px;color:#9aa4b2;text-transform:uppercase">Active users</div>
  <div style="font-size:28px;font-weight:700;color:#e6e9ef">1,284</div>
  <div style="font-size:12px;color:#51cf66">▲ 12%</div>
</div>
```

Give 2-4 genuinely distinct options. **Because the preview may not render
(see the reality check above), the label + description must stand on their own.**
Near-identical options aren't a real choice.

## Channel B — standalone HTML gallery

For real mockups that deserve full rendering, build one self-contained `.html`
showing options **side by side** as cards, each with a live preview, and let the
user select. Selection returns via the same copy-paste-back token.

1. Start from `../assets/options-template.html`.
2. Inline `../assets/design-system.css` and `../assets/copy-back.js`.
3. One `.option` card per choice in a `.grid cols-2/3`. Each: a **rendered
   preview** (real HTML/CSS or inline SVG), a title, a sentence on what it
   optimizes for, and a radio (pick one) / checkbox (pick several).
4. `CopyBack.init({ required: ['choice'] })` so copy stays disabled until a pick.
5. Surface the file; tell the user to click, Copy, paste back.
6. On paste-back, parse the token, **confirm the pick in one line**, proceed.

## Making options good (both channels)

- **Distinct, not shades** — each option meaningfully changes the outcome.
- **Name the tradeoff** under each ("Dense — more on screen, busier" vs
  "Airy — calmer, more scrolling"), not a bare label.
- **Show, don't describe** — a rendered preview beats an adjective.
- **Mark your recommendation** if you have one, but still let them choose, and
  always allow an **"Other / none of these"** path.
- **~3 options.** Two feels thin, five is paralysis.
- **Confirm the selection** back before acting on it.
