# Wireframe canvas

Low-fidelity UI mockups inside an MDX design doc. Deliberately grayscale and
boxy — wireframe altitude, not pixel-perfect. That's the right level for
communicating a design without bikeshedding visuals.

All tags are registered globally — no imports.

## Layout: `<Canvas>` and `<Screen>`

- `<Canvas>` — a scrollable surface that lays out screens left-to-right, wrapping.
- `<Screen name title? width?>` — one artboard with a title bar. `name` is the
  short label (e.g. `Login`), `title` an optional caption, `width` in px
  (default 320).

## Primitives

| Tag | Renders | Props |
|---|---|---|
| `<WBox h?>` | dashed container | `h` min-height px; takes children |
| `<WText lines?>` | placeholder text lines | `lines` (default 1) |
| `<WButton>` | filled button | children = label |
| `<WInput placeholder?>` | input field | `placeholder` |
| `<WImage h?>` | image placeholder | `h` min-height px (default 80) |
| `<WRow>` | horizontal flex of children | — |
| `<WCol>` | vertical stack of children | — |

## `--wf-*` design tokens

Defined in `runner/src/components/wireframe/tokens.css`: `--wf-bg`,
`--wf-surface`, `--wf-line`, `--wf-fill`, `--wf-text`, `--wf-radius`. Override
in a doc only if you must; the defaults keep every wireframe consistent.

## Example

```mdx
<Canvas>
  <Screen name="Login" title="Signed-out">
    <WText lines={1} />
    <WInput placeholder="email" />
    <WInput placeholder="password" />
    <WButton>Sign in</WButton>
  </Screen>
  <Screen name="Home" title="Signed-in">
    <WRow>
      <WImage h={48} />
      <WText lines={2} />
    </WRow>
    <WBox h={120}>main content</WBox>
  </Screen>
</Canvas>
```

Keep prose around the canvas explaining the flow — the wireframe shows layout,
the prose carries intent.
