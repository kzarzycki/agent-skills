import type { ComponentType } from "react";
import { docs } from "virtual:mdx-docs";

export interface DocEntry {
  slug: string;
  title: string;
  load: () => Promise<{ default: ComponentType }>;
}

export function loadDocs(): DocEntry[] {
  return docs as DocEntry[];
}
