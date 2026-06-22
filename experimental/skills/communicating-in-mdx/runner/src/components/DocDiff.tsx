import { useState, useMemo, type ReactNode } from "react";
import { diffWordsWithSpace } from "diff";
import { sources } from "virtual:mdx-docs";
import { Rendered } from "./mdxRender";
import MermaidDiff from "./MermaidDiff";

// A rendered, section-matched diff of two MDX documents. Sections are matched by
// H2 heading and marked same / changed / added / removed. `same`, `added`, and
// `removed` sections render through the real MDX pipeline (rich). `changed`
// sections get word-level highlighting (red removed / green added) in one of two
// layouts: `split` (two columns) or `inline` (single unified, tracked-changes
// style). `auto` picks per section: tables → split, prose/lists → inline.

type Status = "same" | "changed" | "added" | "removed";
type Mode = "auto" | "split" | "inline";

interface Section {
  key: string;
  heading: string | null;
  body: string;
}

const INTRO_KEY = "\0intro";

// Split into the preamble (H1 + lead) plus one section per H2, ignoring `##`
// that falls inside a fenced code block.
function splitSections(src: string): Section[] {
  const lines = src.split("\n");
  const out: Section[] = [];
  let heading: string | null = null;
  let key = INTRO_KEY;
  let buf: string[] = [];
  let fence: string | null = null;
  const flush = () => out.push({ key, heading, body: buf.join("\n").trim() });
  for (const line of lines) {
    const fm = /^(```+|~~~+)/.exec(line);
    if (fm) {
      if (fence && line.startsWith(fence)) fence = null;
      else if (!fence) fence = fm[1];
    }
    const h = !fence ? /^##\s+(.+?)\s*$/.exec(line) : null;
    if (h) {
      flush();
      heading = h[1];
      key = h[1].trim().toLowerCase();
      buf = [];
    } else {
      buf.push(line);
    }
  }
  flush();
  return out.filter((s, i) => !(i === 0 && s.heading === null && !s.body));
}

const norm = (s: string) => s.replace(/\s+/g, " ").trim();

interface Row {
  key: string;
  heading: string;
  status: Status;
  a?: Section;
  b?: Section;
}

function buildRows(srcA: string, srcB: string): Row[] {
  const a = splitSections(srcA);
  const b = splitSections(srcB);
  const aMap = new Map(a.map((s) => [s.key, s]));
  const bMap = new Map(b.map((s) => [s.key, s]));
  const order: string[] = b.map((s) => s.key);
  for (const s of a) if (!bMap.has(s.key)) order.push(s.key); // removed → append
  return order.map((key) => {
    const av = aMap.get(key);
    const bv = bMap.get(key);
    const label = (bv ?? av)!.heading ?? "(intro)";
    let status: Status;
    if (av && bv) status = norm(av.body) === norm(bv.body) ? "same" : "changed";
    else if (bv) status = "added";
    else status = "removed";
    return { key, heading: label, status, a: av, b: bv };
  });
}

// ── Block model ───────────────────────────────────────────────────────────
// A changed section is broken into blocks so each kind diffs at the right
// granularity. Highlight marks are applied to TEXT only (rendered as spans),
// never injected into MDX source — that would break table pipes / `**` / `` ` ``.

type Block =
  | { kind: "table"; head: string[]; body: string[][] }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "code"; text: string }
  | { kind: "para"; text: string };

function splitCells(row: string): string[] {
  let r = row.trim();
  if (r.startsWith("|")) r = r.slice(1);
  if (r.endsWith("|")) r = r.slice(0, -1);
  return r.split("|").map((c) => c.trim());
}

const isSep = (l: string) => /^\s*\|?\s*:?-{2,}/.test(l) && l.includes("-");
const listMarker = /^\s*([-*+]|\d+[.)])\s+/;

function classify(lines: string[]): Block {
  const first = lines[0] ?? "";
  if (/^(```+|~~~+)/.test(first)) return { kind: "code", text: lines.join("\n") };
  const piped = lines.filter((l) => l.includes("|"));
  if (lines.length >= 2 && piped.length >= 2 && isSep(lines[1])) {
    const head = splitCells(lines[0]);
    const body = lines.slice(2).filter((l) => l.includes("|")).map(splitCells);
    return { kind: "table", head, body };
  }
  if (listMarker.test(first)) {
    const ordered = /^\s*\d+[.)]\s+/.test(first);
    const items: string[] = [];
    for (const l of lines) {
      if (listMarker.test(l)) items.push(l.replace(listMarker, ""));
      else if (items.length) items[items.length - 1] += " " + l.trim();
    }
    return { kind: "list", ordered, items };
  }
  return { kind: "para", text: lines.join(" ") };
}

// Block boundaries = blank lines, but a fenced code block stays whole.
function parseBlocks(body: string): Block[] {
  const out: Block[] = [];
  let buf: string[] = [];
  let fence: string | null = null;
  const flush = () => {
    if (buf.join("").trim()) out.push(classify(buf));
    buf = [];
  };
  for (const line of body.split("\n")) {
    const fm = /^(```+|~~~+)/.exec(line);
    if (fence) {
      buf.push(line);
      if (line.startsWith(fence)) {
        fence = null;
        flush();
      }
      continue;
    }
    if (fm) {
      flush();
      fence = fm[1];
      buf.push(line);
      continue;
    }
    if (line.trim() === "") flush();
    else buf.push(line);
  }
  if (fence) flush();
  flush();
  return out;
}

// ── Word-diff renderers ─────────────────────────────────────────────────────
const SIDE_A = "a" as const;
const SIDE_B = "b" as const;
type Side = typeof SIDE_A | typeof SIDE_B;

// One side of a split view: common + (removed on A | added on B).
function sideSpans(aText: string, bText: string, side: Side): ReactNode[] {
  const parts = diffWordsWithSpace(aText ?? "", bText ?? "");
  const out: ReactNode[] = [];
  parts.forEach((p, i) => {
    if (p.added) {
      if (side === SIDE_B) out.push(<ins key={i} className="docdiff__ins">{p.value}</ins>);
    } else if (p.removed) {
      if (side === SIDE_A) out.push(<del key={i} className="docdiff__del">{p.value}</del>);
    } else {
      out.push(<span key={i}>{p.value}</span>);
    }
  });
  return out;
}

// Unified (inline) view: removed + added interleaved as tracked-changes markup.
function unifiedSpans(aText: string, bText: string): ReactNode[] {
  return diffWordsWithSpace(aText ?? "", bText ?? "").map((p, i) =>
    p.added ? (
      <ins key={i} className="docdiff__ins">{p.value}</ins>
    ) : p.removed ? (
      <del key={i} className="docdiff__del">{p.value}</del>
    ) : (
      <span key={i}>{p.value}</span>
    ),
  );
}

const asTable = (b?: Block) => (b && b.kind === "table" ? b : null);
const asList = (b?: Block) => (b && b.kind === "list" ? b : null);
const aText = (b?: Block) => (b && (b.kind === "para" || b.kind === "code") ? b.text : "");

// A ```mermaid fence: diffed as a rendered diagram, not as source text.
const isMermaidBlock = (b?: Block): b is Extract<Block, { kind: "code" }> =>
  !!b && b.kind === "code" && /^[ \t]*(```+|~~~+)\s*mermaid\b/i.test(b.text);

function cell(a: Block | null, b: Block | null, r: number, c: number) {
  const av = a && a.kind === "table" ? (r === 0 ? a.head[c] : a.body[r - 1]?.[c]) ?? "" : "";
  const bv = b && b.kind === "table" ? (r === 0 ? b.head[c] : b.body[r - 1]?.[c]) ?? "" : "";
  return [av, bv] as const;
}

// Render a single block for split side / inline. `a`/`b` are the matched blocks.
function renderBlock(aB: Block | undefined, bB: Block | undefined, layout: "a" | "b" | "inline"): ReactNode {
  const self = layout === SIDE_A ? aB : layout === SIDE_B ? bB : (bB ?? aB);
  if (!self) return null;
  const a = aB && aB.kind === self.kind ? aB : undefined;
  const b = bB && bB.kind === self.kind ? bB : undefined;

  if (self.kind === "table") {
    const at = asTable(a);
    const bt = asTable(b);
    const cols = Math.max(at?.head.length ?? 0, bt?.head.length ?? 0);
    const rowsA = at ? at.body.length + 1 : 0;
    const rowsB = bt ? bt.body.length + 1 : 0;
    const nRows = layout === SIDE_A ? rowsA : layout === SIDE_B ? rowsB : Math.max(rowsA, rowsB);
    const renderCell = (r: number, c: number, tag: "th" | "td") => {
      const [av, bv] = cell(at, bt, r, c);
      const nodes =
        layout === "inline" ? unifiedSpans(av, bv) : sideSpans(av, bv, layout as Side);
      return tag === "th" ? <th key={c}>{nodes}</th> : <td key={c}>{nodes}</td>;
    };
    return (
      <table className="docdiff__table">
        <thead>
          <tr>{Array.from({ length: cols }, (_, c) => renderCell(0, c, "th"))}</tr>
        </thead>
        <tbody>
          {Array.from({ length: Math.max(0, nRows - 1) }, (_, i) => (
            <tr key={i}>{Array.from({ length: cols }, (_, c) => renderCell(i + 1, c, "td"))}</tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (self.kind === "list") {
    const al = asList(a);
    const bl = asList(b);
    const ordered = (asList(self) ?? al ?? bl)?.ordered ?? false;
    const Tag = ordered ? "ol" : "ul";
    const n =
      layout === SIDE_A
        ? al?.items.length ?? 0
        : layout === SIDE_B
          ? bl?.items.length ?? 0
          : Math.max(al?.items.length ?? 0, bl?.items.length ?? 0);
    return (
      <Tag className="docdiff__list">
        {Array.from({ length: n }, (_, i) => {
          const av = al?.items[i] ?? "";
          const bv = bl?.items[i] ?? "";
          return (
            <li key={i}>
              {layout === "inline" ? unifiedSpans(av, bv) : sideSpans(av, bv, layout as Side)}
            </li>
          );
        })}
      </Tag>
    );
  }

  // para / code
  const av = aText(a);
  const bv = aText(b);
  const nodes = layout === "inline" ? unifiedSpans(av, bv) : sideSpans(av, bv, layout as Side);
  return self.kind === "code" ? (
    <pre className="docdiff__code">
      <code>{nodes}</code>
    </pre>
  ) : (
    <p>{nodes}</p>
  );
}

function HighlightedChange({
  a,
  b,
  mode,
  labels,
}: {
  a?: Section;
  b?: Section;
  mode: "split" | "inline";
  labels: [string, string];
}) {
  const aBlocks = useMemo(() => parseBlocks(a?.body ?? ""), [a?.body]);
  const bBlocks = useMemo(() => parseBlocks(b?.body ?? ""), [b?.body]);
  const n = Math.max(aBlocks.length, bBlocks.length);
  const pairs = Array.from({ length: n }, (_, i) => [aBlocks[i], bBlocks[i]] as const);

  // Mermaid fences diff as rendered diagrams (full width, below the text diff).
  const mermaid = pairs.filter(([ab, bb]) => isMermaidBlock(ab) || isMermaidBlock(bb));
  const text = pairs.filter(([ab, bb]) => !(isMermaidBlock(ab) || isMermaidBlock(bb)));

  const textView =
    mode === "inline" ? (
      <div className="docdiff__inline docdiff__blocks">
        {text.map(([ab, bb], i) => (
          <div key={i}>{renderBlock(ab, bb, "inline")}</div>
        ))}
      </div>
    ) : (
      <div className="docdiff__cols">
        <div className="docdiff__col docdiff__col--a docdiff__blocks">
          {text.map(([ab, bb], i) => (
            <div key={i}>{renderBlock(ab, bb, "a")}</div>
          ))}
        </div>
        <div className="docdiff__col docdiff__col--b docdiff__blocks">
          {text.map(([ab, bb], i) => (
            <div key={i}>{renderBlock(ab, bb, "b")}</div>
          ))}
        </div>
      </div>
    );

  return (
    <>
      {text.length > 0 && textView}
      {mermaid.map(([ab, bb], i) => (
        <MermaidDiff
          key={`m${i}`}
          before={isMermaidBlock(ab) ? ab.text : undefined}
          after={isMermaidBlock(bb) ? bb.text : undefined}
          labels={labels}
        />
      ))}
    </>
  );
}

// Auto heuristic: a section that contains a table compares best side-by-side
// (aligned cells); prose / list changes read best inline (intra-sentence flow).
function effectiveMode(r: Row, mode: Mode): "split" | "inline" {
  if (mode !== "auto") return mode;
  const hasTable = parseBlocks(r.b?.body ?? r.a?.body ?? "").some((bl) => bl.kind === "table");
  return hasTable ? "split" : "inline";
}

// same/added/removed panes render rich via the shared MDX pipeline (./mdxRender).
function Pane({ section, missing }: { section?: Section; missing: string }) {
  if (!section) return <div className="docdiff__missing">{missing}</div>;
  return <Rendered source={section.body} />;
}

const MODES: Mode[] = ["auto", "split", "inline"];

export default function DocDiff({
  a,
  b,
  labels = ["before", "after"],
  mode: initialMode = "auto",
}: {
  a: string;
  b: string;
  labels?: [string, string];
  mode?: Mode;
}) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const srcA = sources[a];
  const srcB = sources[b];
  const rows = useMemo(
    () => (srcA != null && srcB != null ? buildRows(srcA, srcB) : []),
    [srcA, srcB],
  );

  if (srcA == null || srcB == null) {
    const missing = [srcA == null && a, srcB == null && b].filter(Boolean).join(", ");
    return <div className="docdiff__err">DocDiff: source doc(s) not found: {missing}</div>;
  }

  const counts = rows.reduce(
    (m, r) => ((m[r.status] = (m[r.status] ?? 0) + 1), m),
    {} as Record<Status, number>,
  );

  return (
    <div className="docdiff">
      <div className="docdiff__bar">
        <span className="docdiff__legend">
          <b>{rows.length}</b> sections ·{" "}
          {(["changed", "added", "removed", "same"] as Status[])
            .filter((s) => counts[s])
            .map((s) => (
              <span key={s} className={`docdiff__badge docdiff__badge--${s}`}>
                {counts[s]} {s}
              </span>
            ))}
        </span>
        <span className="docdiff__toolbar">
          <span className="docdiff__modes" role="group" aria-label="diff layout">
            {MODES.map((m) => (
              <button
                key={m}
                type="button"
                className={`docdiff__mode${mode === m ? " is-active" : ""}`}
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
              >
                {m}
              </button>
            ))}
          </span>
          <span className="docdiff__labels">
            <span className="docdiff__label docdiff__label--a">{labels[0]}</span>
            <span className="docdiff__label docdiff__label--b">{labels[1]}</span>
          </span>
        </span>
      </div>

      {rows.map((r) => (
        <section key={r.key} className={`docdiff__sec docdiff__sec--${r.status}`}>
          <header className="docdiff__head">
            <span className="docdiff__title">{r.heading}</span>
            <span className="docdiff__tags">
              {r.status === "changed" && (
                <span className="docdiff__badge docdiff__badge--mode">{effectiveMode(r, mode)}</span>
              )}
              <span className={`docdiff__badge docdiff__badge--${r.status}`}>{r.status}</span>
            </span>
          </header>
          {r.status === "same" ? (
            <details className="docdiff__same">
              <summary>unchanged — click to view</summary>
              <div className="docdiff__col">
                <Pane section={r.b ?? r.a} missing="—" />
              </div>
            </details>
          ) : r.status === "changed" ? (
            <HighlightedChange a={r.a} b={r.b} mode={effectiveMode(r, mode)} labels={labels} />
          ) : (
            <div className="docdiff__cols">
              <div className="docdiff__col docdiff__col--a">
                <Pane section={r.a} missing={`— not in ${labels[0]} —`} />
              </div>
              <div className="docdiff__col docdiff__col--b">
                <Pane section={r.b} missing={`— removed in ${labels[1]} —`} />
              </div>
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
