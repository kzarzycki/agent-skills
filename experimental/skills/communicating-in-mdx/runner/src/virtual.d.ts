declare module "virtual:mdx-docs" {
  import type { ComponentType } from "react";
  export const docs: {
    slug: string;
    title: string;
    load: () => Promise<{ default: ComponentType }>;
  }[];
  export const sources: Record<string, string>;
}
