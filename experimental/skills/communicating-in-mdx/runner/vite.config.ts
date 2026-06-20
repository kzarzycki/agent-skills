import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import mdx from "@mdx-js/rollup";
import path from "node:path";
import { answersPlugin } from "./answers-plugin";
import { docsPlugin } from "./docs-plugin";

const docsDir = process.env.MDX_DOCS_DIR;
const answersFile = process.env.MDX_ANSWERS_FILE;

export default defineConfig({
  // Pin the cache inside the runner. Without this, Vite resolves cacheDir from
  // the nearest ancestor package.json, so under npx/symlinked invocations the
  // `.vite` dir escapes into the repo root and shows up as untracked noise.
  cacheDir: path.resolve(__dirname, "node_modules/.vite"),
  plugins: [
    { enforce: "pre", ...mdx({ providerImportSource: "@mdx-js/react" }) },
    react(),
    docsPlugin(docsDir),
    ...(answersFile ? [answersPlugin(answersFile)] : []),
  ],
  server: {
    port: Number(process.env.MDX_RUNNER_PORT) || 5173,
    fs: { allow: [path.resolve(__dirname), ...(docsDir ? [docsDir] : [])] },
  },
  // Pre-bundle every dep up front. Otherwise Vite discovers mermaid/shiki late
  // (when a doc that uses them first renders), re-optimizes, and full-reloads —
  // and that mid-session reload can 500 the `virtual:mdx-docs` module. Declaring
  // them here keeps the initial optimize complete so no late reload ever fires.
  optimizeDeps: {
    include: [
      "react",
      "react-dom",
      "react-dom/client",
      "react/jsx-runtime",
      "react/jsx-dev-runtime",
      "@mdx-js/react",
      "mermaid",
      "shiki",
    ],
  },
  // Docs live outside the runner and are symlinked in as `.docs`. Preserving
  // symlinks resolves their imports (@mdx-js/react, react/jsx-runtime) through
  // the symlink path against the runner's node_modules, not the doc's real path.
  resolve: { preserveSymlinks: true },
});
