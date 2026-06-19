import type { ReactNode } from "react";

export default function Columns({ children }: { children?: ReactNode }) {
  return <div className="columns">{children}</div>;
}
