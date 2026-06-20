import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { docsPlugin } from "./docs-plugin";

export default defineConfig({
  // Pin the cache inside the runner so the vitest `.vite` dir can't escape into
  // an ancestor (the skill dir / repo root) and surface as untracked noise.
  cacheDir: path.resolve(__dirname, "node_modules/.vite"),
  // docsPlugin() with no dir resolves `virtual:mdx-docs` to an empty list so
  // docs.ts imports cleanly under test. react()/docsPlugin are vite 6 plugins;
  // the cast bridges vitest's bundled vite 5 types.
  plugins: [react() as never, docsPlugin() as never],
  test: { environment: "jsdom", globals: true, setupFiles: ["./test/setup.ts"] },
});
