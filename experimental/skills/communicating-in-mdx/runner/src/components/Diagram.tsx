import { useMemo, useState } from "react";

export type DiagramNode = {
  id: string;
  x: number;
  y: number;
  w?: number;
  h?: number;
  label: string;
  tip?: string;
};
export type DiagramEdge = { from: string; to: string; label?: string };

const NW = 130;
const NH = 52;

export function Diagram({
  nodes,
  edges = [],
  height = 300,
}: {
  nodes: DiagramNode[];
  edges?: DiagramEdge[];
  height?: number;
}) {
  const [active, setActive] = useState<string | null>(null);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const activeTip = active ? byId[active]?.tip : undefined;

  return (
    <div
      className="diagram"
      style={{ height }}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setPos({ x: e.clientX - r.left, y: e.clientY - r.top });
      }}
    >
      <svg className="diagram__edges">
        {edges.map((ed, i) => {
          const a = byId[ed.from];
          const b = byId[ed.to];
          if (!a || !b) return null;
          const ax = a.x + (a.w ?? NW) / 2;
          const ay = a.y + (a.h ?? NH) / 2;
          const bx = b.x + (b.w ?? NW) / 2;
          const by = b.y + (b.h ?? NH) / 2;
          const on = active === ed.from || active === ed.to;
          return (
            <line
              key={i}
              x1={ax}
              y1={ay}
              x2={bx}
              y2={by}
              className={`diagram__edge${on ? " active" : ""}`}
            />
          );
        })}
      </svg>
      {nodes.map((n) => (
        <div
          key={n.id}
          className={`diagram__node${active === n.id ? " active" : ""}`}
          style={{ left: n.x, top: n.y, width: n.w ?? NW, height: n.h ?? NH }}
          onMouseEnter={() => setActive(n.id)}
          onMouseLeave={() => setActive((cur) => (cur === n.id ? null : cur))}
        >
          {n.label}
        </div>
      ))}
      {activeTip && (
        <div className="diagram__tip" style={{ left: pos.x + 14, top: pos.y + 14 }} role="tooltip">
          {activeTip}
        </div>
      )}
    </div>
  );
}
