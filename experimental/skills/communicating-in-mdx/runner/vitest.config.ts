import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // react() resolves to the app's vite 6 Plugin type; vitest's config expects its
  // bundled vite 5 type. The cast bridges the two vite majors (test-only config).
  plugins: [react() as never],
  test: { environment: "jsdom", globals: true, setupFiles: ["./test/setup.ts"] },
});
