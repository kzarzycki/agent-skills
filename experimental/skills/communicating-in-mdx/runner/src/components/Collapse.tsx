import type { ReactNode } from "react";

export default function Collapse({
  summary,
  open,
  children,
}: {
  summary: string;
  open?: boolean;
  children?: ReactNode;
}) {
  return (
    <details className="collapse" open={open}>
      <summary>{summary}</summary>
      <div className="collapse__body">{children}</div>
    </details>
  );
}
