# Charts without dependencies

Prefer hand-written inline SVG. It's tiny, themeable via CSS variables, and
keeps the file offline-safe. Reach for a CDN charting library only when the
user explicitly needs interactivity (tooltips, zoom) — and tell them the file
then needs network on first open.

## Bar chart (inline SVG)

```html
<svg viewBox="0 0 320 160" width="100%" role="img" aria-label="Monthly bars">
  <!-- baseline -->
  <line x1="0" y1="150" x2="320" y2="150" stroke="var(--border)"/>
  <!-- bars: x, height computed from value -->
  <rect x="20"  y="60"  width="40" height="90"  rx="4" fill="var(--accent)"/>
  <rect x="80"  y="30"  width="40" height="120" rx="4" fill="var(--accent)"/>
  <rect x="140" y="90"  width="40" height="60"  rx="4" fill="var(--accent)"/>
  <rect x="200" y="50"  width="40" height="100" rx="4" fill="var(--accent)"/>
  <rect x="260" y="20"  width="40" height="130" rx="4" fill="var(--accent-2)"/>
</svg>
```

Compute `y = 150 - (value / max) * 130` and `height = 150 - y`.

## Line / sparkline (inline SVG)

```html
<svg viewBox="0 0 320 100" width="100%" aria-label="Trend">
  <polyline fill="none" stroke="var(--accent)" stroke-width="2"
            points="0,80 50,60 100,65 150,40 200,45 250,20 300,25"/>
</svg>
```

Map each point: `x = i/(n-1)*300`, `y = 90 - (v/max)*80`.

## Donut (single percentage)

```html
<svg viewBox="0 0 120 120" width="120" height="120" aria-label="72%">
  <circle cx="60" cy="60" r="50" fill="none" stroke="var(--surface-2)" stroke-width="14"/>
  <!-- dasharray = 2*pi*r = 314; offset = 314*(1 - pct) -->
  <circle cx="60" cy="60" r="50" fill="none" stroke="var(--accent)" stroke-width="14"
          stroke-dasharray="314" stroke-dashoffset="88" stroke-linecap="round"
          transform="rotate(-90 60 60)"/>
  <text x="60" y="66" text-anchor="middle" font-size="22" font-weight="700"
        fill="var(--text)">72%</text>
</svg>
```

## Slideshow scaffold (only for the slideshow format)

```html
<style>
  .slide { min-height: 100vh; display: grid; place-content: center;
           scroll-snap-align: start; padding: 8vh 6vw; }
  html { scroll-snap-type: y mandatory; }
</style>
<section class="slide">...</section>
<section class="slide">...</section>
<script>
  // optional: arrow-key paging
  document.addEventListener('keydown', e => {
    const slides = [...document.querySelectorAll('.slide')];
    const i = slides.findIndex(s => s.getBoundingClientRect().top >= -2);
    if (e.key === 'ArrowDown' && slides[i+1]) slides[i+1].scrollIntoView({behavior:'smooth'});
    if (e.key === 'ArrowUp'   && slides[i-1]) slides[i-1].scrollIntoView({behavior:'smooth'});
  });
</script>
```
