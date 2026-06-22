import { type ReactNode } from "react";
import { diffWordsWithSpace } from "diff";
import Mermaid from "./Mermaid";

// A diff of two mermaid diagrams. Both sides are rendered as real diagrams; in
// the after diagram nodes are recoloured green=added / amber=changed, and in the
// before diagram red=removed / amber=changed. Detection is line-level on
// flowchart node definitions (`id["label"]`, `id(...)`, `id{...}`): same id with
// a changed definition line = changed, id only on one side = added/removed. Edge
// label changes don't recolour a node but show in the source diff below. When a
// side is absent (added/removed whole diagram) the present side renders plain.

const FENCE = /^[ \t]*(```+|~~~+)[^\n]*\n?|\n?[ \t]*(```+|~~~+)[ \t]*$/g;
const stripFence = (text: string) => text.replace(FENCE, "").trim();

// Lines that declare a node with a label: `Browser["…"]`, `A(x)`, `A{x}`.
const DEF = /^([A-Za-z0-9_][\w-]*)\s*[[({]/;
const SKIP = /^(graph|flowchart|subgraph|end|classDef|class|linkStyle|style|direction|click|%%)/;

function defs(src: string): Map<string, string> {
  const m = new Map<string, string>();
  for (const raw of src.split("\n")) {
    const t = raw.trim();
    if (SKIP.test(t)) continue;
    const d = DEF.exec(t);
    if (d) m.set(d[1], t);
  }
  return m;
}

const CLASSDEFS = [
  "classDef ddAdd fill:#0b5d2e,stroke:#21d07a,color:#fff;",
  "classDef ddRem fill:#5d1a1a,stroke:#ff6b6b,color:#fff;",
].join("\n");

// Append classDef + class statements so the named nodes are recoloured.
function styled(src: string, marks: { ddAdd?: string[]; ddRem?: string[] }): string {
  const lines = Object.entries(marks)
    .filter(([, ids]) => ids && ids.length)
    .map(([cls, ids]) => `class ${ids!.join(",")} ${cls};`);
  if (!lines.length) return src;
  return `${src}\n${CLASSDEFS}\n${lines.join("\n")}`;
}

function sourceDiff(a: string, b: string): ReactNode[] {
  return diffWordsWithSpace(a, b).map((p, i) =>
    p.added ? (
      <ins key={i} className="docdiff__ins">{p.value}</ins>
    ) : p.removed ? (
      <del key={i} className="docdiff__del">{p.value}</del>
    ) : (
      <span key={i}>{p.value}</span>
    ),
  );
}

function Pane({ title, chart, tone }: { title: string; chart: string; tone: string }) {
  return (
    <figure className={`docdiff__mpane docdiff__mpane--${tone}`}>
      <figcaption>{title}</figcaption>
      <Mermaid chart={chart} />
    </figure>
  );
}

export default function MermaidDiff({
  before,
  after,
  labels = ["previous", "current"],
}: {
  before?: string;
  after?: string;
  labels?: [string, string];
}) {
  const a = before ? stripFence(before) : "";
  const b = after ? stripFence(after) : "";

  // Whole-diagram added / removed: render the one present side plainly.
  if (!a || !b) {
    const present = b || a;
    const tone = b ? "added" : "removed";
    return (
      <div className="docdiff__mermaid">
        <Pane title={`${tone === "added" ? labels[1] : labels[0]} — diagram ${tone}`} chart={present} tone={tone} />
      </div>
    );
  }

  const da = defs(a);
  const db = defs(b);
  const added: string[] = [];
  const removed: string[] = [];
  const changed: string[] = [];
  for (const id of db.keys()) {
    if (!da.has(id)) added.push(id);
    else if (da.get(id) !== db.get(id)) changed.push(id);
  }
  for (const id of da.keys()) if (!db.has(id)) removed.push(id);

  // Red/green per side, matching the word-diff: the previous pane shows what's
  // going away (removed + the old form of changed nodes) in red; the current
  // pane shows what's new (added + the new form of changed nodes) in green.
  const beforeChart = styled(a, { ddRem: [...removed, ...changed] });
  const afterChart = styled(b, { ddAdd: [...added, ...changed] });

  return (
    <div className="docdiff__mermaid">
      <div className="docdiff__mlegend">
        <span className="docdiff__mkey docdiff__mkey--rem">removed / changed-from</span>
        <span className="docdiff__mkey docdiff__mkey--add">added / changed-to</span>
      </div>
      <div className="docdiff__mpanes">
        <Pane title={labels[0]} chart={beforeChart} tone="a" />
        <Pane title={labels[1]} chart={afterChart} tone="b" />
      </div>
      <details className="docdiff__msource">
        <summary>diagram source diff</summary>
        <pre className="docdiff__code"><code>{sourceDiff(a, b)}</code></pre>
      </details>
    </div>
  );
}
