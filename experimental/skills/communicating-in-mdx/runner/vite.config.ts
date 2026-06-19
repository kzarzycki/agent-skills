import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import mdx from "@mdx-js/rollup";
import path from "node:path";
import { answersPlugin } from "./answers-plugin";

const docsDir = process.env.MDX_DOCS_DIR;
const answersFile = process.env.MDX_ANSWERS_FILE;

export default defineConfig({
  plugins: [
    { enforce: "pre", ...mdx({ providerImportSource: "@mdx-js/react" }) },
    react(),
    ...(answersFile ? [answersPlugin(answersFile)] : []),
  ],
  server: {
    port: Number(process.env.MDX_RUNNER_PORT) || 5173,
    fs: { allow: [path.resolve(__dirname), ...(docsDir ? [docsDir] : [])] },
  },
  // Docs live outside the runner and are symlinked in as `.docs`. Preserving
  // symlinks resolves their imports (@mdx-js/react, react/jsx-runtime) through
  // the symlink path against the runner's node_modules, not the doc's real path.
  resolve: { preserveSymlinks: true },
});
