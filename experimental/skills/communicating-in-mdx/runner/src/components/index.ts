import type { ComponentType } from "react";

// Each component task adds its export here. MDXProvider registers these globally
// so .mdx documents use the tags without importing.
export const components: Record<string, ComponentType<any>> = {};
