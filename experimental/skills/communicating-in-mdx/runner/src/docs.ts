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
