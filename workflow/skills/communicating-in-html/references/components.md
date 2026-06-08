# Component vocabulary

Copy-paste HTML blocks that pair with `../assets/design-system.css`. All classes
are already styled — just fill in content. Inline the CSS into the page first.

## KPI grid (dashboard top row)

```html
<div class="grid cols-4">
  <div class="card kpi">
    <span class="label">Revenue</span>
    <span class="value">$1.28M</span>
    <span class="delta up">▲ 12% vs last Q</span>
  </div>
  <div class="card kpi">
    <span class="label">Active users</span>
    <span class="value">8,420</span>
    <span class="delta down">▼ 3%</span>
  </div>
  <!-- ...2 more... -->
</div>
```

## Card

```html
<div class="card">
  <h3>Section title</h3>
  <p class="muted">Supporting line.</p>
</div>
```

## Callout (highlight / warning / risk)

```html
<div class="callout ok"><strong>Verdict:</strong> Ship it.</div>
<div class="callout warn"><strong>Watch:</strong> Latency trending up.</div>
<div class="callout danger"><strong>Blocker:</strong> No rollback path.</div>
```

## Table with inline bars and status badges

```html
<table>
  <thead>
    <tr><th>Item</th><th class="num">Score</th><th>Share</th><th>Status</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>Checkout flow</td>
      <td class="num">92</td>
      <td><div class="bar"><span style="width:92%"></span></div></td>
      <td><span class="badge ok">Pass</span></td>
    </tr>
    <tr>
      <td>Search</td>
      <td class="num">61</td>
      <td><div class="bar"><span style="width:61%;background:var(--warn)"></span></div></td>
      <td><span class="badge warn">Review</span></td>
    </tr>
  </tbody>
</table>
```

## Progress meter (single value in prose)

```html
<div class="meter">
  <span>Coverage</span>
  <div class="bar"><span style="width:78%"></span></div>
  <strong>78%</strong>
</div>
```

## Two-column comparison

```html
<div class="grid cols-2">
  <div class="card"><h3>Option A</h3>...</div>
  <div class="card"><h3>Option B</h3>...</div>
</div>
```

## Eyebrow + headline (section opener)

```html
<p class="eyebrow">Q2 Review</p>
<h2>What moved the number</h2>
```
