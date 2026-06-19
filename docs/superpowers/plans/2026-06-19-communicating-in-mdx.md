# communicating-in-mdx Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `communicating-in-mdx` skill — a fully-local MDX enrichment layer where MDX is the artifact and a bundled Vite+React dev server renders it.

**Architecture:** The skill ships a self-contained Vite+React runner. A CLI (`bin/mdx-runner.mjs`) symlinks an external docs directory into the runner as `.docs`, sets `MDX_DOCS_DIR` for Vite's `server.fs.allow`, and spawns Vite. The React app globs `../.docs/**/*.mdx`, lists documents, and renders the selected one with a globally-registered component library (via `@mdx-js/react` MDXProvider) — so `.mdx` files need no imports. No network calls; no HTML deliverable.

**Tech Stack:** Vite 6, React 18, `@mdx-js/rollup` + `@mdx-js/react` 3, mermaid 11, shiki 1, Vitest 2 + Testing Library, TypeScript 5.

## Global Constraints

- Skill lives at `experimental/skills/communicating-in-mdx/` in the agent-skills repo. Runner at `.../runner/`.
- No remote services, no telemetry, no uploads. The runner makes zero outbound network calls at runtime.
- Components are registered globally; `.mdx` documents MUST NOT need `import` statements.
- Authoring principle baked into docs: prose-first, components-as-enhancement; raw `.mdx` must still read as Markdown.
- All dependency versions pinned via caret majors above; `package-lock.json` is committed.
- Conventional Commits for every commit (`feat:`, `chore:`, `docs:`, `test:`).
- Runner is dev-server only in v1 — no `vite build` single-file export feature.
- Work happens on branch `docs/communicating-in-mdx-spec` (already checked out) or a fresh `feat/communicating-in-mdx` branch off it.

---

### Task 1: Runner scaffold (Vite + React + MDX, empty shell)

**Files:**
- Create: `experimental/skills/communicating-in-mdx/runner/package.json`
- Create: `experimental/skills/communicating-in-mdx/runner/tsconfig.json`
- Create: `experimental/skills/communicating-in-mdx/runner/vite.config.ts`
- Create: `experimental/skills/communicating-in-mdx/runner/index.html`
- Create: `experimental/skills/communicating-in-mdx/runner/src/main.tsx`
- Create: `experimental/skills/communicating-in-mdx/runner/src/App.tsx`
- Create: `experimental/skills/communicating-in-mdx/runner/vitest.config.ts`
- Create: `experimental/skills/communicating-in-mdx/runner/test/setup.ts`
- Test: `experimental/skills/communicating-in-mdx/runner/test/app.test.tsx`

**Interfaces:**
- Produces: `App` (default export, React component). Renders a `<main class="app">` shell with an empty state when no docs. Consumed by Task 3 (doc index) and `main.tsx`.

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "communicating-in-mdx-runner",
  "private": true,
  "type": "module",
  "version": "0.1.0",
  "bin": { "mdx-runner": "./bin/mdx-runner.mjs" },
  "scripts": {
    "dev": "vite",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "@mdx-js/react": "^3.1.0",
    "mermaid": "^11.4.0",
    "shiki": "^1.24.0"
  },
  "devDependencies": {
    "vite": "^6.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "@mdx-js/rollup": "^3.1.0",
    "typescript": "^5.7.0",
    "vitest": "^2.1.0",
    "jsdom": "^25.0.0",
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0"
  }
}
```

- [ ] **Step 2: Write `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "types": ["vite/client", "vitest/globals", "@testing-library/jest-dom"],
    "lib": ["ES2022", "DOM", "DOM.Iterable"]
  },
  "include": ["src", "test", "vite.config.ts", "vitest.config.ts"]
}
```

- [ ] **Step 3: Write `vite.config.ts`** (MDX plugin must precede React plugin; `providerImportSource` enables global components; `fs.allow` admits the external docs dir)

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import mdx from "@mdx-js/rollup";
import path from "node:path";

const docsDir = process.env.MDX_DOCS_DIR;

export default defineConfig({
  plugins: [
    { enforce: "pre", ...mdx({ providerImportSource: "@mdx-js/react" }) },
    react(),
  ],
  server: {
    port: Number(process.env.MDX_RUNNER_PORT) || 5173,
    fs: { allow: [path.resolve(__dirname), ...(docsDir ? [docsDir] : [])] },
  },
});
```

- [ ] **Step 4: Write `index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>MDX Runner</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Write `src/App.tsx`** (empty shell for now; Task 3 fills the index)

```tsx
export default function App() {
  return (
    <main className="app">
      <p className="app__empty">No .mdx documents found in this directory.</p>
    </main>
  );
}
```

- [ ] **Step 6: Write `src/main.tsx`**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 7: Write `vitest.config.ts` and `test/setup.ts`**

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", globals: true, setupFiles: ["./test/setup.ts"] },
});
```

```ts
// test/setup.ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 8: Write the failing test `test/app.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import App from "../src/App";

test("renders empty state when no docs", () => {
  render(<App />);
  expect(screen.getByText(/no .mdx documents found/i)).toBeInTheDocument();
});
```

- [ ] **Step 9: Install and run test**

Run: `cd experimental/skills/communicating-in-mdx/runner && npm install && npm test`
Expected: PASS (1 test).

- [ ] **Step 10: Commit**

```bash
git add experimental/skills/communicating-in-mdx/runner
git commit -m "feat: scaffold communicating-in-mdx Vite+React+MDX runner"
```

---

### Task 2: CLI launcher with `--dir`, `--open`, `--port`, `--check`

**Files:**
- Create: `experimental/skills/communicating-in-mdx/runner/bin/mdx-runner.mjs`
- Test: `experimental/skills/communicating-in-mdx/runner/test/cli.test.mjs`

**Interfaces:**
- Produces: `parseArgs(argv): { dir, open, port, check }` and `prepare(dir): { docsDir, symlinkPath }` (named exports). `prepare` resolves `dir` to absolute, validates it exists, and creates/refreshes a `.docs` symlink at the runner root pointing to it. The default export `run(argv)` calls both, then (unless `check`) spawns Vite with `MDX_DOCS_DIR` set.
- Consumed by: the user/agent at the shell; Task 9 (runner.md docs).

- [ ] **Step 1: Write the failing test `test/cli.test.mjs`**

```js
import { test, expect } from "vitest";
import { mkdtempSync, realpathSync, lstatSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { parseArgs, prepare } from "../bin/mdx-runner.mjs";

test("parseArgs reads dir, open, port, check", () => {
  const a = parseArgs(["--dir", "/x/y", "--open", "--port", "6000", "--check"]);
  expect(a).toEqual({ dir: "/x/y", open: true, port: "6000", check: true });
});

test("parseArgs defaults dir to .work-or-docs sentinel", () => {
  expect(parseArgs([]).dir).toBe(null);
});

test("prepare creates a .docs symlink to the resolved dir", () => {
  const target = mkdtempSync(path.join(tmpdir(), "mdx-docs-"));
  const { docsDir, symlinkPath } = prepare(target);
  expect(docsDir).toBe(realpathSync(target));
  expect(lstatSync(symlinkPath).isSymbolicLink()).toBe(true);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- cli`
Expected: FAIL ("Cannot find module ../bin/mdx-runner.mjs").

- [ ] **Step 3: Write `bin/mdx-runner.mjs`**

```js
#!/usr/bin/env node
import { existsSync, lstatSync, rmSync, symlinkSync, realpathSync, statSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const runnerRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

export function parseArgs(argv) {
  const a = { dir: null, open: false, port: null, check: false };
  for (let i = 0; i < argv.length; i++) {
    const v = argv[i];
    if (v === "--dir") a.dir = argv[++i];
    else if (v === "--open") a.open = true;
    else if (v === "--port") a.port = argv[++i];
    else if (v === "--check") a.check = true;
  }
  return a;
}

// Resolve the docs dir: explicit --dir, else .work/ if present, else docs/, relative to cwd.
export function resolveDir(dir) {
  if (dir) return path.resolve(dir);
  const cwd = process.cwd();
  for (const cand of [".work", "docs"]) {
    const p = path.join(cwd, cand);
    if (existsSync(p) && statSync(p).isDirectory()) return p;
  }
  return cwd;
}

export function prepare(dir) {
  const docsDir = realpathSync(resolveDir(dir));
  const symlinkPath = path.join(runnerRoot, ".docs");
  if (existsSync(symlinkPath) || (() => { try { lstatSync(symlinkPath); return true; } catch { return false; } })())
    rmSync(symlinkPath, { force: true });
  symlinkSync(docsDir, symlinkPath, "dir");
  return { docsDir, symlinkPath };
}

export function run(argv) {
  const args = parseArgs(argv);
  const { docsDir } = prepare(args.dir);
  console.log(`[mdx-runner] serving ${docsDir}`);
  if (args.check) return 0;
  const viteArgs = [];
  if (args.open) viteArgs.push("--open");
  const child = spawn("npx", ["vite", ...viteArgs], {
    cwd: runnerRoot,
    stdio: "inherit",
    env: { ...process.env, MDX_DOCS_DIR: docsDir, MDX_RUNNER_PORT: args.port || "" },
  });
  child.on("exit", (code) => process.exit(code ?? 0));
}

if (import.meta.url === `file://${process.argv[1]}`) run(process.argv.slice(2));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- cli`
Expected: PASS (3 tests).

- [ ] **Step 5: Smoke-test `--check` headlessly**

Run: `mkdir -p /tmp/mdxcheck && node bin/mdx-runner.mjs --dir /tmp/mdxcheck --check`
Expected: prints `[mdx-runner] serving /private/tmp/mdxcheck` (or resolved path) and exits 0. Verify `.docs` symlink now exists in the runner root, then `rm .docs`.

- [ ] **Step 6: Add `.docs` to skill `.gitignore`**

Create `experimental/skills/communicating-in-mdx/runner/.gitignore`:
```
node_modules
.docs
dist
```

- [ ] **Step 7: Commit**

```bash
git add experimental/skills/communicating-in-mdx/runner/bin experimental/skills/communicating-in-mdx/runner/test/cli.test.mjs experimental/skills/communicating-in-mdx/runner/.gitignore
git commit -m "feat: add mdx-runner CLI with --dir symlink and --check mode"
```

---

### Task 3: Document discovery, index, and MDX rendering with global components

**Files:**
- Create: `experimental/skills/communicating-in-mdx/runner/src/docs.ts`
- Modify: `experimental/skills/communicating-in-mdx/runner/src/App.tsx`
- Create: `experimental/skills/communicating-in-mdx/runner/src/components/index.ts`
- Modify: `experimental/skills/communicating-in-mdx/runner/src/main.tsx`
- Create: `experimental/skills/communicating-in-mdx/runner/test/.docs-fixture/sample.mdx`
- Test: `experimental/skills/communicating-in-mdx/runner/test/docs.test.tsx`

**Interfaces:**
- Produces: `loadDocs(): DocEntry[]` where `DocEntry = { slug: string; title: string; load: () => Promise<{ default: React.ComponentType }> }`. Consumed by `App`.
- Produces: `components` (record of tag→component) in `components/index.ts`. Initially `{}`; each later task adds its component here. Consumed by `main.tsx` MDXProvider.

- [ ] **Step 1: Write `src/docs.ts`**

```ts
import type { ComponentType } from "react";

export interface DocEntry {
  slug: string;
  title: string;
  load: () => Promise<{ default: ComponentType }>;
}

export function loadDocs(): DocEntry[] {
  const mods = import.meta.glob("../.docs/**/*.mdx");
  return Object.entries(mods)
    .map(([file, load]) => {
      const slug = file.replace("../.docs/", "").replace(/\.mdx$/, "");
      const title = slug.split("/").pop()!.replace(/[-_]/g, " ");
      return { slug, title, load: load as DocEntry["load"] };
    })
    .sort((a, b) => a.slug.localeCompare(b.slug));
}
```

- [ ] **Step 2: Write `src/components/index.ts`**

```ts
import type { ComponentType } from "react";

// Each component task adds its export here. MDXProvider registers these globally
// so .mdx documents use the tags without importing.
export const components: Record<string, ComponentType<any>> = {};
```

- [ ] **Step 3: Rewrite `src/main.tsx` to wrap App in MDXProvider**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MDXProvider } from "@mdx-js/react";
import App from "./App";
import { components } from "./components";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MDXProvider components={components}>
      <App />
    </MDXProvider>
  </StrictMode>,
);
```

- [ ] **Step 4: Rewrite `src/App.tsx` (index + lazy render, hash routing)**

```tsx
import { Suspense, lazy, useMemo, useSyncExternalStore } from "react";
import { loadDocs } from "./docs";

function useHash() {
  return useSyncExternalStore(
    (cb) => (window.addEventListener("hashchange", cb), () => window.removeEventListener("hashchange", cb)),
    () => window.location.hash.slice(1),
  );
}

export default function App() {
  const docs = useMemo(() => loadDocs(), []);
  const slug = useHash();
  const current = docs.find((d) => d.slug === slug);

  if (docs.length === 0)
    return <main className="app"><p className="app__empty">No .mdx documents found in this directory.</p></main>;

  return (
    <div className="layout">
      <nav className="sidebar">
        <h2 className="sidebar__title">Documents</h2>
        <ul>{docs.map((d) => (
          <li key={d.slug}><a href={`#${d.slug}`} className={d.slug === slug ? "active" : ""}>{d.title}</a></li>
        ))}</ul>
      </nav>
      <main className="app">
        {current ? <DocView entry={current} /> : <p className="app__empty">Select a document.</p>}
      </main>
    </div>
  );
}

function DocView({ entry }: { entry: ReturnType<typeof loadDocs>[number] }) {
  const Doc = useMemo(() => lazy(entry.load), [entry.slug]);
  return <article className="doc"><Suspense fallback={<p>Loading…</p>}><Doc /></Suspense></article>;
}
```

- [ ] **Step 5: Write fixture `test/.docs-fixture/sample.mdx`**

```mdx
# Sample Doc

Hello from MDX.
```

- [ ] **Step 6: Write the failing test `test/docs.test.tsx`** (point the glob at the fixture by mocking)

```tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../src/docs", () => ({
  loadDocs: () => [
    { slug: "sample", title: "sample", load: async () => ({ default: () => <h1>Sample Doc</h1> }) },
  ],
}));

import App from "../src/App";

test("lists docs and renders the selected one via hash", async () => {
  window.location.hash = "#sample";
  render(<App />);
  expect(screen.getByRole("link", { name: /sample/i })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: /sample doc/i })).toBeInTheDocument();
});
```

- [ ] **Step 7: Run test**

Run: `npm test -- docs`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add experimental/skills/communicating-in-mdx/runner/src experimental/skills/communicating-in-mdx/runner/test
git commit -m "feat: add MDX doc discovery, sidebar index, and global component provider"
```

---

### Task 4: Design system + app shell styles

**Files:**
- Create: `experimental/skills/communicating-in-mdx/runner/src/styles/design-system.css`
- Modify: `experimental/skills/communicating-in-mdx/runner/src/main.tsx` (import the CSS)

**Interfaces:**
- Produces: CSS custom properties (`--bg`, `--fg`, `--muted`, `--accent`, `--border`, `--radius`, spacing scale) and layout classes (`.layout`, `.sidebar`, `.app`, `.doc`). Consumed visually by all components.

- [ ] **Step 1: Write `src/styles/design-system.css`** (adapt tokens from `communicating-in-html/assets/design-system.css`; dark theme, system font stack, readable measure)

```css
:root {
  --bg: #0f1115; --surface: #161922; --fg: #e7e9ee; --muted: #9aa3b2;
  --accent: #6ea8fe; --border: #262b36; --radius: 8px;
  --ok: #5ad19a; --warn: #f0b454; --danger: #f06d6d;
  --s1: 4px; --s2: 8px; --s3: 12px; --s4: 16px; --s5: 24px; --s6: 40px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); line-height: 1.6; }
.layout { display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }
.sidebar { border-right: 1px solid var(--border); padding: var(--s5); background: var(--surface); }
.sidebar__title { font-size: 13px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
.sidebar ul { list-style: none; padding: 0; margin: 0; }
.sidebar a { display: block; padding: var(--s2) var(--s3); color: var(--fg); text-decoration: none; border-radius: var(--radius); }
.sidebar a:hover, .sidebar a.active { background: var(--bg); color: var(--accent); }
.app { padding: var(--s6); }
.app__empty { color: var(--muted); }
.doc { max-width: 760px; margin: 0 auto; }
.doc h1, .doc h2, .doc h3 { line-height: 1.25; }
.doc pre { background: var(--surface); padding: var(--s4); border-radius: var(--radius); overflow-x: auto; }
.doc code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
@media (max-width: 720px) { .layout { grid-template-columns: 1fr; } .sidebar { border-right: none; border-bottom: 1px solid var(--border); } }
```

- [ ] **Step 2: Import CSS in `src/main.tsx`**

Add at top: `import "./styles/design-system.css";`

- [ ] **Step 3: Verify build compiles**

Run: `npx vite build` (from runner dir)
Expected: build succeeds, no CSS import errors. (Then `rm -rf dist`.)

- [ ] **Step 4: Commit**

```bash
git add experimental/skills/communicating-in-mdx/runner/src/styles experimental/skills/communicating-in-mdx/runner/src/main.tsx
git commit -m "feat: add MDX runner design system and app shell styles"
```

---

### Task 5: Static document components — Callout, Columns, Checklist, FileTree, MetricCard, Steps/Timeline

These share one pattern: a styled wrapper over children/props with no async or interactive state. One task, one CSS file, complete code for each, registered together.

**Files:**
- Create: `.../runner/src/components/Callout.tsx`, `Columns.tsx`, `Checklist.tsx`, `FileTree.tsx`, `MetricCard.tsx`, `Steps.tsx`
- Create: `.../runner/src/components/components.css`
- Modify: `.../runner/src/components/index.ts` (register all six)
- Modify: `.../runner/src/main.tsx` (import `components/components.css`)
- Test: `.../runner/test/static-components.test.tsx`

**Interfaces:**
- Produces (all default exports):
  - `Callout({ tone?: "info"|"decision"|"warn"|"danger", title?: string, children })`
  - `Columns({ children })` — flex row of children
  - `Checklist({ items: string[] })` or children `<li>`; supports `items` prop
  - `FileTree({ tree: string })` — preformatted indented tree
  - `MetricCard({ label, value, delta?, tone? })`
  - `Steps({ children })` / `Timeline` alias — ordered visual steps
- All registered in `components` record under tag names `Callout`, `Columns`, `Checklist`, `FileTree`, `MetricCard`, `Steps`, `Timeline`.

- [ ] **Step 1: Write the failing test `test/static-components.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import Callout from "../src/components/Callout";
import MetricCard from "../src/components/MetricCard";
import Checklist from "../src/components/Checklist";
import { components } from "../src/components";

test("Callout shows tone class and children", () => {
  render(<Callout tone="decision" title="Pick one">body</Callout>);
  expect(screen.getByText("Pick one")).toBeInTheDocument();
  expect(screen.getByText("body").closest(".callout")).toHaveClass("callout--decision");
});

test("MetricCard renders label and value", () => {
  render(<MetricCard label="Tokens" value="1.2k" delta="-30%" />);
  expect(screen.getByText("Tokens")).toBeInTheDocument();
  expect(screen.getByText("1.2k")).toBeInTheDocument();
});

test("Checklist renders items", () => {
  render(<Checklist items={["a", "b"]} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});

test("registry exposes all six tags", () => {
  ["Callout", "Columns", "Checklist", "FileTree", "MetricCard", "Steps", "Timeline"]
    .forEach((t) => expect(components[t]).toBeTruthy());
});
```

- [ ] **Step 2: Run to verify failure** — `npm test -- static-components` → FAIL (modules missing).

- [ ] **Step 3: Write the six components**

```tsx
// Callout.tsx
export default function Callout({ tone = "info", title, children }: { tone?: "info"|"decision"|"warn"|"danger"; title?: string; children?: React.ReactNode }) {
  return (
    <aside className={`callout callout--${tone}`}>
      {title && <p className="callout__title">{title}</p>}
      <div className="callout__body">{children}</div>
    </aside>
  );
}
```

```tsx
// Columns.tsx
export default function Columns({ children }: { children?: React.ReactNode }) {
  return <div className="columns">{children}</div>;
}
```

```tsx
// Checklist.tsx
export default function Checklist({ items, children }: { items?: string[]; children?: React.ReactNode }) {
  if (items) return <ul className="checklist">{items.map((it, i) => <li key={i}>{it}</li>)}</ul>;
  return <ul className="checklist">{children}</ul>;
}
```

```tsx
// FileTree.tsx
export default function FileTree({ tree, children }: { tree?: string; children?: React.ReactNode }) {
  return <pre className="filetree">{tree ?? children}</pre>;
}
```

```tsx
// MetricCard.tsx
export default function MetricCard({ label, value, delta, tone = "info" }: { label: string; value: string; delta?: string; tone?: "info"|"ok"|"warn"|"danger" }) {
  return (
    <div className={`metric metric--${tone}`}>
      <span className="metric__label">{label}</span>
      <span className="metric__value">{value}</span>
      {delta && <span className="metric__delta">{delta}</span>}
    </div>
  );
}
```

```tsx
// Steps.tsx
export default function Steps({ children }: { children?: React.ReactNode }) {
  return <ol className="steps">{children}</ol>;
}
export { Steps as Timeline };
```

- [ ] **Step 4: Write `components/components.css`** (styles for `.callout`, `.callout--*`, `.columns`, `.checklist`, `.filetree`, `.metric`, `.steps`). Include tone colors using `--accent/--warn/--danger/--ok`. (Implementer writes ~40 lines mapping each class; tones set left-border + tinted background.)

- [ ] **Step 5: Register in `components/index.ts`**

```ts
import Callout from "./Callout";
import Columns from "./Columns";
import Checklist from "./Checklist";
import FileTree from "./FileTree";
import MetricCard from "./MetricCard";
import Steps, { Timeline } from "./Steps";
// ... assign into the `components` record:
Object.assign(components, { Callout, Columns, Checklist, FileTree, MetricCard, Steps, Timeline });
```

- [ ] **Step 6: Import CSS in `main.tsx`** — add `import "./components/components.css";`

- [ ] **Step 7: Run test** — `npm test -- static-components` → PASS.

- [ ] **Step 8: Commit** — `git commit -m "feat: add static MDX document components (callout, columns, checklist, filetree, metriccard, steps)"`

---

### Task 6: Interactive components — Tabs, Collapse

**Files:**
- Create: `.../src/components/Tabs.tsx`, `Collapse.tsx`
- Modify: `components/index.ts` (register), `components.css` (styles)
- Test: `.../test/interactive-components.test.tsx`

**Interfaces:**
- Produces: `Tabs({ labels: string[], children })` — children are panels, one per label; clicking a tab switches panel via local `useState`. `Collapse({ summary, children, open? })` — uses native `<details>`.

- [ ] **Step 1: Write failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event"; // add to devDeps if missing; else use fireEvent
import Tabs from "../src/components/Tabs";

test("Tabs switches panels", async () => {
  render(<Tabs labels={["One", "Two"]}><p>first</p><p>second</p></Tabs>);
  expect(screen.getByText("first")).toBeVisible();
  await userEvent.click(screen.getByRole("tab", { name: "Two" }));
  expect(screen.getByText("second")).toBeVisible();
});
```

(If `@testing-library/user-event` is not desired, use `fireEvent.click`. Add `@testing-library/user-event@^14` to devDependencies in that case.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

```tsx
// Tabs.tsx
import { Children, useState } from "react";
export default function Tabs({ labels, children }: { labels: string[]; children: React.ReactNode }) {
  const [i, setI] = useState(0);
  const panels = Children.toArray(children);
  return (
    <div className="tabs">
      <div className="tabs__bar" role="tablist">
        {labels.map((l, k) => (
          <button key={k} role="tab" aria-selected={k === i} className={k === i ? "active" : ""} onClick={() => setI(k)}>{l}</button>
        ))}
      </div>
      <div className="tabs__panel" role="tabpanel">{panels[i]}</div>
    </div>
  );
}
```

```tsx
// Collapse.tsx
export default function Collapse({ summary, open, children }: { summary: string; open?: boolean; children?: React.ReactNode }) {
  return <details className="collapse" open={open}><summary>{summary}</summary><div className="collapse__body">{children}</div></details>;
}
```

- [ ] **Step 4: Register + style + run test → PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add interactive Tabs and Collapse components"`

---

### Task 7: Code components — Diff and AnnotatedCode (Shiki highlighting)

**Files:**
- Create: `.../src/components/Diff.tsx`, `AnnotatedCode.tsx`, `src/lib/highlighter.ts`
- Modify: `components/index.ts`, `components.css`
- Test: `.../test/code-components.test.tsx`

**Interfaces:**
- Produces: `getHighlighter()` singleton (lazy `shiki.createHighlighter`, themes `["github-dark"]`, common langs). `Diff({ code, lang? })` — renders lines, `+`/`-` prefixes tinted. `AnnotatedCode({ code, lang?, notes? })` where `notes: { line: number; text: string }[]` renders code with margin notes anchored by line.

- [ ] **Step 1: Failing test**

```tsx
import { render, screen } from "@testing-library/react";
import Diff from "../src/components/Diff";

test("Diff tints added and removed lines", () => {
  render(<Diff code={"+added\n-removed\n unchanged"} />);
  expect(screen.getByText("added").closest(".diff__line")).toHaveClass("diff__line--add");
  expect(screen.getByText("removed").closest(".diff__line")).toHaveClass("diff__line--del");
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `src/lib/highlighter.ts`**

```ts
import { createHighlighter, type Highlighter } from "shiki";
let hl: Promise<Highlighter> | null = null;
export function getHighlighter() {
  if (!hl) hl = createHighlighter({ themes: ["github-dark"], langs: ["ts", "tsx", "js", "json", "bash", "css", "html", "python"] });
  return hl;
}
```

- [ ] **Step 4: Implement `Diff.tsx`** (parse lines by first char; Shiki optional for inner syntax, but tinting is the core; keep Shiki for `AnnotatedCode`)

```tsx
export default function Diff({ code }: { code: string }) {
  return (
    <pre className="diff"><code>{code.split("\n").map((line, i) => {
      const cls = line.startsWith("+") ? "diff__line--add" : line.startsWith("-") ? "diff__line--del" : "diff__line--ctx";
      return <span key={i} className={`diff__line ${cls}`}>{line.replace(/^[+\- ]/, "")}{"\n"}</span>;
    })}</code></pre>
  );
}
```

- [ ] **Step 5: Implement `AnnotatedCode.tsx`** (Shiki to HTML in `useEffect`, render notes in a margin column keyed by line)

```tsx
import { useEffect, useState } from "react";
import { getHighlighter } from "../lib/highlighter";
export default function AnnotatedCode({ code, lang = "ts", notes = [] }: { code: string; lang?: string; notes?: { line: number; text: string }[] }) {
  const [html, setHtml] = useState("");
  useEffect(() => { let live = true; getHighlighter().then((h) => { if (live) setHtml(h.codeToHtml(code, { lang, theme: "github-dark" })); }); return () => { live = false; }; }, [code, lang]);
  return (
    <div className="annotated">
      <div className="annotated__code" dangerouslySetInnerHTML={{ __html: html }} />
      {notes.length > 0 && <ul className="annotated__notes">{notes.map((n, i) => <li key={i}><b>L{n.line}</b> {n.text}</li>)}</ul>}
    </div>
  );
}
```

- [ ] **Step 6: Register + style + run test → PASS.** (Diff test does not need Shiki; AnnotatedCode async render verified by a `findBy` if added.)
- [ ] **Step 7: Commit** — `git commit -m "feat: add Diff and AnnotatedCode components with shiki highlighting"`

---

### Task 8: Mermaid component

**Files:**
- Create: `.../src/components/Mermaid.tsx`
- Modify: `components/index.ts`, `components.css`
- Test: `.../test/mermaid.test.tsx`

**Interfaces:**
- Produces: `Mermaid({ chart: string })` or children string. Renders via `mermaid.render` in `useEffect`; mocked in tests (mermaid needs a real DOM/measurement).

- [ ] **Step 1: Failing test (mock mermaid)**

```tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("mermaid", () => ({ default: { initialize: vi.fn(), render: vi.fn(async () => ({ svg: "<svg data-testid='m'></svg>" })) } }));
import Mermaid from "../src/components/Mermaid";
test("renders mermaid svg", async () => {
  render(<Mermaid chart="graph TD; A-->B" />);
  expect(await screen.findByTestId("m")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `Mermaid.tsx`**

```tsx
import { useEffect, useId, useState } from "react";
import mermaid from "mermaid";
mermaid.initialize({ startOnLoad: false, theme: "dark" });
export default function Mermaid({ chart, children }: { chart?: string; children?: string }) {
  const id = useId().replace(/:/g, "");
  const [svg, setSvg] = useState("");
  const src = (chart ?? (typeof children === "string" ? children : "")).trim();
  useEffect(() => { let live = true; mermaid.render(`m${id}`, src).then((r) => { if (live) setSvg(r.svg); }).catch(() => {}); return () => { live = false; }; }, [src, id]);
  return <div className="mermaid" dangerouslySetInnerHTML={{ __html: svg }} />;
}
```

- [ ] **Step 4: Register + run test → PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: add Mermaid diagram component"`

---

### Task 9: QuestionForm with copy-back token

**Files:**
- Create: `.../src/components/QuestionForm.tsx`, `src/lib/copyback.ts`
- Modify: `components/index.ts`, `components.css`
- Test: `.../test/questionform.test.tsx`, `.../test/copyback.test.ts`

**Interfaces:**
- Produces: `serializeAnswers(answers: Record<string,string>): string` → `ANSWERS<<<\n{json}\n>>>ANSWERS`. `QuestionForm({ questions })` where `questions: { id: string; label: string; type?: "text"|"choice"; options?: string[] }[]`. Renders inputs, a "Copy answers" button that writes the token to clipboard and shows it in a `<textarea readonly>` for manual copy.

- [ ] **Step 1: Failing tests**

```ts
// copyback.test.ts
import { serializeAnswers } from "../src/lib/copyback";
test("wraps JSON in ANSWERS token", () => {
  const t = serializeAnswers({ a: "1" });
  expect(t.startsWith("ANSWERS<<<")).toBe(true);
  expect(t.includes('"a": "1"')).toBe(true);
  expect(t.trim().endsWith(">>>ANSWERS")).toBe(true);
});
```

```tsx
// questionform.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import QuestionForm from "../src/components/QuestionForm";
test("collects answers into token textarea", () => {
  render(<QuestionForm questions={[{ id: "name", label: "Name" }]} />);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Zarz" } });
  fireEvent.click(screen.getByRole("button", { name: /copy answers/i }));
  expect((screen.getByRole("textbox", { name: /answers token/i }) as HTMLTextAreaElement).value).toContain('"name": "Zarz"');
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `src/lib/copyback.ts`**

```ts
export function serializeAnswers(answers: Record<string, string>): string {
  return `ANSWERS<<<\n${JSON.stringify(answers, null, 2)}\n>>>ANSWERS`;
}
```

- [ ] **Step 4: Implement `QuestionForm.tsx`**

```tsx
import { useState } from "react";
import { serializeAnswers } from "../lib/copyback";
type Q = { id: string; label: string; type?: "text" | "choice"; options?: string[] };
export default function QuestionForm({ questions }: { questions: Q[] }) {
  const [ans, setAns] = useState<Record<string, string>>({});
  const [token, setToken] = useState("");
  const set = (id: string, v: string) => setAns((p) => ({ ...p, [id]: v }));
  const emit = () => { const t = serializeAnswers(ans); setToken(t); navigator.clipboard?.writeText(t).catch(() => {}); };
  return (
    <form className="qform" onSubmit={(e) => e.preventDefault()}>
      {questions.map((q) => (
        <label key={q.id} className="qform__field">
          <span>{q.label}</span>
          {q.type === "choice" && q.options
            ? <select aria-label={q.label} onChange={(e) => set(q.id, e.target.value)}><option value="" /> {q.options.map((o) => <option key={o} value={o}>{o}</option>)}</select>
            : <input aria-label={q.label} onChange={(e) => set(q.id, e.target.value)} />}
        </label>
      ))}
      <button type="button" onClick={emit}>Copy answers</button>
      {token && <textarea aria-label="answers token" className="qform__token" readOnly value={token} rows={6} />}
    </form>
  );
}
```

- [ ] **Step 5: Register + style + run tests → PASS.**
- [ ] **Step 6: Commit** — `git commit -m "feat: add QuestionForm with copy-back answer token"`

---

### Task 10: Wireframe canvas — tokens, primitives, Canvas, Screen

**Files:**
- Create: `.../src/components/wireframe/tokens.css`, `primitives.tsx`, `Canvas.tsx`, `Screen.tsx`
- Modify: `components/index.ts`, `main.tsx` (import tokens.css)
- Test: `.../test/wireframe.test.tsx`

**Interfaces:**
- Produces:
  - `Canvas({ children })` — scrollable artboard surface laying out `<Screen>`s in a wrapping flex grid.
  - `Screen({ name, title?, width?, children })` — a device-frame artboard.
  - Primitives `WBox`, `WText`, `WButton`, `WInput`, `WImage`, `WRow`, `WCol` — low-fi placeholder elements styled by `--wf-*` tokens.
- All registered under their tag names.

- [ ] **Step 1: Failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { Canvas, Screen } from "../src/components/wireframe/Canvas"; // re-exported
import { WButton } from "../src/components/wireframe/primitives";
test("Screen shows its name and renders primitives", () => {
  render(<Canvas><Screen name="Login"><WButton>Sign in</WButton></Screen></Canvas>);
  expect(screen.getByText("Login")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `tokens.css`** (`--wf-bg`, `--wf-line`, `--wf-fill`, `--wf-text`, `--wf-radius`; muted grayscale wireframe palette).

- [ ] **Step 4: Implement `primitives.tsx`**

```tsx
export const WBox = ({ children, h }: { children?: React.ReactNode; h?: number }) => <div className="wf-box" style={h ? { minHeight: h } : undefined}>{children}</div>;
export const WText = ({ lines = 1 }: { lines?: number }) => <div className="wf-text">{Array.from({ length: lines }).map((_, i) => <span key={i} className="wf-text__line" />)}</div>;
export const WButton = ({ children }: { children?: React.ReactNode }) => <button className="wf-button" type="button">{children}</button>;
export const WInput = ({ placeholder }: { placeholder?: string }) => <div className="wf-input">{placeholder}</div>;
export const WImage = ({ h = 80 }: { h?: number }) => <div className="wf-image" style={{ minHeight: h }} aria-label="image placeholder" />;
export const WRow = ({ children }: { children?: React.ReactNode }) => <div className="wf-row">{children}</div>;
export const WCol = ({ children }: { children?: React.ReactNode }) => <div className="wf-col">{children}</div>;
```

- [ ] **Step 5: Implement `Canvas.tsx`** (and re-export Screen)

```tsx
export function Canvas({ children }: { children?: React.ReactNode }) {
  return <div className="wf-canvas">{children}</div>;
}
export function Screen({ name, title, width = 320, children }: { name: string; title?: string; width?: number; children?: React.ReactNode }) {
  return (
    <section className="wf-screen" style={{ width }}>
      <header className="wf-screen__bar"><span className="wf-screen__name">{name}</span>{title && <span className="wf-screen__title">{title}</span>}</header>
      <div className="wf-screen__body">{children}</div>
    </section>
  );
}
```

- [ ] **Step 6: Register all wireframe tags in `components/index.ts`; import `tokens.css` in `main.tsx`.**
- [ ] **Step 7: Run test → PASS.**
- [ ] **Step 8: Commit** — `git commit -m "feat: add wireframe canvas (Canvas, Screen, low-fi primitives)"`

---

### Task 11: SKILL.md and reference docs

**Files:**
- Create: `experimental/skills/communicating-in-mdx/SKILL.md`
- Create: `.../references/when-mdx.md`, `components.md`, `wireframe.md`, `runner.md`
- Create: `.../assets/starter.mdx`

**Interfaces:** No code. Content must satisfy the spec.

- [ ] **Step 1: Write `SKILL.md`** — frontmatter `name: communicating-in-mdx` + a one-line description. Body must cover, mirroring `communicating-in-html`'s structure:
  - The enrichment-layer framing (prefer MDX for specs/plans/designs/recaps/reports when loaded; zero-coupling).
  - The decision heuristic table (when MDX beats Markdown/HTML) — point to `references/when-mdx.md`.
  - The authoring principles: prose-first/components-as-enhancement, no imports, author from the registry.
  - The component vocabulary as a compact table (tag → use), pointing to `references/components.md`.
  - How to render: `node <skill>/runner/bin/mdx-runner.mjs --dir <project>/.work --open`, run in a tmux window `mdx-runner`, start/stop autonomously; point to `references/runner.md`.
  - Delivery: write `kebab-case.mdx` into `.work/`/`docs/`, leave a 3-5 bullet TL;DR in chat.
  - Coexistence note with `communicating-in-html` (MDX for rich/iterated docs with Node; HTML for zero-dep one-offs).

- [ ] **Step 2: Write `references/components.md`** — the authoritative registry: every tag, its props (copy signatures from Tasks 5-10 verbatim), and a 3-6 line MDX usage example each. This is the file the skill tells Claude to read before authoring.

- [ ] **Step 3: Write `references/wireframe.md`** — the canvas system: Canvas/Screen, every primitive, the `--wf-*` tokens, and a complete `<Canvas>` example with two `<Screen>`s.

- [ ] **Step 4: Write `references/when-mdx.md`** — MDX vs HTML vs Markdown doctrine (adapt `communicating-in-html/references/when-html.md`): when each wins, the cost (toolchain dependency), the degrade-to-Markdown property.

- [ ] **Step 5: Write `references/runner.md`** — install (`npm install` in runner once), the CLI flags, the tmux lifecycle, `--check` for headless verification, troubleshooting (port in use, stale `.docs` symlink, fs.allow).

- [ ] **Step 6: Write `assets/starter.mdx`** — a complete exemplar document that exercises Callout, Steps, Diff, Mermaid, Columns, MetricCard, and one small `<Canvas>` — prose-first, demonstrating the house style.

- [ ] **Step 7: Commit** — `git commit -m "docs: add communicating-in-mdx SKILL.md, references, and starter exemplar"`

---

### Task 12: Plugin registration and skill listing

**Files:**
- Modify: whatever registers experimental skills for the agent-skills plugin (check `.claude-plugin/` and how `communicating-in-html` is listed; mirror it exactly).

- [ ] **Step 1: Inspect how `communicating-in-html` is registered** (`grep -r communicating-in-html .claude-plugin/ *.json`).
- [ ] **Step 2: Add `communicating-in-mdx` the same way.**
- [ ] **Step 3: Commit** — `git commit -m "chore: register communicating-in-mdx skill"`

---

### Task 13: End-to-end verification + human acceptance gate

**Files:**
- Create: `experimental/skills/communicating-in-mdx/runner/test/e2e-build.test.mjs` (optional headless render check)

- [ ] **Step 1: Full unit suite green** — `cd runner && npm test` → all PASS. Record counts.
- [ ] **Step 2: Production build sanity** — `npx vite build` succeeds with the starter doc symlinked; `rm -rf dist`.
- [ ] **Step 3: Headless `--check`** — copy `assets/starter.mdx` into a temp `.work/`, run `node bin/mdx-runner.mjs --dir <temp>/.work --check` → exits 0, symlink resolves.
- [ ] **Step 4: Independent verification (subagent)** — dispatch a fresh subagent to verify against the spec: no network calls in runner src (grep for `fetch`/`http`), no `import` of components inside `.mdx`, prose-first starter, registry matches `components.md`. Subagent returns a PASS/FAIL report with file:line evidence.
- [ ] **Step 5: HUMAN GATE** — start the runner live (`--dir` at the starter doc, `--open`) in a tmux window, give the user `http://localhost:5173`, and ask them to view the rendered starter MDX and accept it. Do not mark the plan complete until the user accepts. If they request changes, loop back to the relevant task.
- [ ] **Step 6: Finalize** — on acceptance, ensure all commits are made; summarize the branch and offer PR via `finishing-a-development-branch`.

---

## Self-Review

**Spec coverage:**
- MDX-is-artifact + local Vite runner → Tasks 1-4. ✓
- `--dir`/tmux/`--check` lifecycle → Task 2, runner.md (Task 11). ✓
- Global MDXProvider, no-import authoring → Task 3 + every component task. ✓
- Document component set (all 11) → Tasks 5-9. ✓
- Wireframe canvas → Task 10. ✓
- QuestionForm copy-back → Task 9. ✓
- SKILL.md + 4 references + starter → Task 11. ✓
- Prose-first / degrade-to-Markdown principle → SKILL.md + when-mdx.md (Task 11). ✓
- Coexistence with HTML skill → SKILL.md (Task 11). ✓
- Pinned deps, no remote calls → Task 1 package.json + Task 13 grep. ✓
- Human acceptance of rendered MDX → Task 13 Step 5. ✓
- Defaults (`.work`/`docs`, port 5173, React, Shiki) → Tasks 1, 2, 4, 7. ✓

**Placeholder scan:** Task 5 Step 4, Task 10 Step 3 and Task 11 leave CSS/prose to the implementer with explicit content requirements rather than full text — acceptable because they are styling/prose, not logic, and the required classes/sections are enumerated. All logic steps show complete code.

**Type consistency:** `components` record (Task 3) is `Object.assign`-extended by every component task — consistent. `DocEntry`/`loadDocs` used identically in `docs.ts` and `App.tsx`. `serializeAnswers` signature identical in Task 9 lib and test. `getHighlighter` returns a `Promise<Highlighter>` used with `.then` in `AnnotatedCode`. Consistent.
