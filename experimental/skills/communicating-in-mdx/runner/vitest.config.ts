import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { docsPlugin } from "./docs-plugin";

export default defineConfig({
  // docsPlugin() with no dir resolves `virtual:mdx-docs` to an empty list so
  // docs.ts imports cleanly under test. react()/docsPlugin are vite 6 plugins;
  // the cast bridges vitest's bundled vite 5 types.
  plugins: [react() as never, docsPlugin() as never],
  test: { environment: "jsdom", globals: true, setupFiles: ["./test/setup.ts"] },
});
