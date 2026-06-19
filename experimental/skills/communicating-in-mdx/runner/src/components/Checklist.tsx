import type { ReactNode } from "react";

export default function Checklist({ items, children }: { items?: string[]; children?: ReactNode }) {
  if (items) {
    return (
      <ul className="checklist">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    );
  }
  return <ul className="checklist">{children}</ul>;
}
