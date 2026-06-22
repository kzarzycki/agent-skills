import { readdirSync, statSync, existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";

const VID = "virtual:mdx-docs";
const RESOLVED = "\0" + VID;

function listMdx(dir: string, base = ""): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const abs = path.join(dir, entry);
    const rel = base ? `${base}/${entry}` : entry;
    if (statSync(abs).isDirectory()) out.push(...listMdx(abs, rel));
    else if (entry.endsWith(".mdx")) out.push(rel);
  }
  return out.sort();
}

// Enumerates the docs directory and exposes the list as `virtual:mdx-docs`.
// Imports go through the `.docs` symlink (so preserveSymlinks resolves the MDX
// runtime against the runner's node_modules). Discovery uses fs — not a glob —
// so adding/removing a doc invalidates the module and reloads, instead of the
// glob-over-symlink emptying on HMR.
export function docsPlugin(docsDir?: string): Plugin {
  return {
    name: "mdx-docs-list",
    resolveId(id) {
      if (id === VID) return RESOLVED;
    },
    load(id) {
      if (id !== RESOLVED) return;
      const files = docsDir && existsSync(docsDir) ? listMdx(docsDir) : [];
      const sources: string[] = [];
      const entries = files.map((rel) => {
        const slug = rel.replace(/\.mdx$/, "");
        const title = (slug.split("/").pop() ?? slug).replace(/[-_]/g, " ");
        const url = "/.docs/" + rel;
        // Raw source is exposed alongside the compiled component so DocDiff can
        // re-render arbitrary versions section-by-section at runtime.
        const raw = docsDir ? readFileSync(path.join(docsDir, rel), "utf8") : "";
        sources.push(`${JSON.stringify(slug)}: ${JSON.stringify(raw)}`);
        return `{ slug: ${JSON.stringify(slug)}, title: ${JSON.stringify(title)}, load: () => import(${JSON.stringify(url)}) }`;
      });
      return `export const docs = [${entries.join(",")}];\nexport const sources = {${sources.join(",")}};`;
    },
    configureServer(server) {
      if (!docsDir) return;
      server.watcher.add(docsDir);
      const onChange = (file: string) => {
        if (!file.endsWith(".mdx")) return;
        const mod = server.moduleGraph.getModuleById(RESOLVED);
        if (mod) server.moduleGraph.invalidateModule(mod);
        server.ws.send({ type: "full-reload" });
      };
      server.watcher.on("add", onChange);
      server.watcher.on("unlink", onChange);
      // Also on content change: the exported `sources` map is read at load time,
      // so an edited doc must re-run load for DocDiff to see the new source.
      server.watcher.on("change", onChange);
    },
  };
}
