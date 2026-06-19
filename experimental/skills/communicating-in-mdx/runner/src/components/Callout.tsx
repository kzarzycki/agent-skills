import type { ReactNode } from "react";

export default function Callout({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "decision" | "warn" | "danger";
  title?: string;
  children?: ReactNode;
}) {
  return (
    <aside className={`callout callout--${tone}`}>
      {title && <p className="callout__title">{title}</p>}
      <div className="callout__body">{children}</div>
    </aside>
  );
}
