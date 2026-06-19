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
