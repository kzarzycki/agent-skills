import type { ComponentType } from "react";
import Callout from "./Callout";
import Columns from "./Columns";
import Checklist from "./Checklist";
import FileTree from "./FileTree";
import MetricCard from "./MetricCard";
import Steps, { Timeline } from "./Steps";
import Tabs from "./Tabs";
import Collapse from "./Collapse";

// MDXProvider registers these globally so .mdx documents use the tags without importing.
export const components: Record<string, ComponentType<any>> = {};

Object.assign(components, {
  Callout,
  Columns,
  Checklist,
  FileTree,
  MetricCard,
  Steps,
  Timeline,
  Tabs,
  Collapse,
});
