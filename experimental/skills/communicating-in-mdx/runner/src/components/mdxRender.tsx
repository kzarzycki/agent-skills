import { useEffect, useState, type ComponentType } from "react";
import * as runtime from "react/jsx-runtime";
import { evaluate } from "@mdx-js/mdx";
import { useMDXComponents } from "@mdx-js/react";
import remarkGfm from "remark-gfm";

// Render an MDX source string at runtime through the real pipeline (remark-gfm
// + the globally-registered components), so tables, callouts, diagrams, and
// custom components render as themselves. Shared by DocDiff (same/added/removed
// panes) and DocInclude (embed a doc's live content). evaluate() is async and
// heavy, so compiled components are cached by source string.
const cache = new Map<string, ComponentType<any>>();

export function Rendered({ source }: { source: string }) {
  const mdxComponents = useMDXComponents();
  const [Comp, setComp] = useState<ComponentType<any> | null>(() => cache.get(source) ?? null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (cache.has(source)) {
      setComp(() => cache.get(source)!);
      return;
    }
    let alive = true;
    evaluate(source, { ...(runtime as any), remarkPlugins: [remarkGfm], baseUrl: import.meta.url })
      .then((mod) => {
        if (!alive) return;
        cache.set(source, mod.default as ComponentType<any>);
        setComp(() => mod.default as ComponentType<any>);
      })
      .catch((e) => alive && setErr(String(e)));
    return () => {
      alive = false;
    };
  }, [source]);
  if (err) return <pre className="docdiff__err">{err}</pre>;
  if (!Comp) return <div className="docdiff__loading">rendering…</div>;
  return <Comp components={mdxComponents} />;
}
