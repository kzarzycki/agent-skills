import { Children, useState, type ReactNode } from "react";

export default function Tabs({ labels, children }: { labels: string[]; children: ReactNode }) {
  const [i, setI] = useState(0);
  const panels = Children.toArray(children);
  return (
    <div className="tabs">
      <div className="tabs__bar" role="tablist">
        {labels.map((l, k) => (
          <button
            key={k}
            role="tab"
            aria-selected={k === i}
            className={k === i ? "active" : ""}
            onClick={() => setI(k)}
          >
            {l}
          </button>
        ))}
      </div>
      <div className="tabs__panel" role="tabpanel">
        {panels[i]}
      </div>
    </div>
  );
}
