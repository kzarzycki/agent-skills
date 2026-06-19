import { readdirSync, statSync, existsSync } from "node:fs";
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
      const entries = files.map((rel) => {
        const slug = rel.replace(/\.mdx$/, "");
        const title = (slug.split("/").pop() ?? slug).replace(/[-_]/g, " ");
        const url = "/.docs/" + rel;
        return `{ slug: ${JSON.stringify(slug)}, title: ${JSON.stringify(title)}, load: () => import(${JSON.stringify(url)}) }`;
      });
      return `export const docs = [${entries.join(",")}];`;
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
    },
  };
}
