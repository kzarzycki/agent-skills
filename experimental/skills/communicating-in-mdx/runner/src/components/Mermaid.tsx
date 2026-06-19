import { useEffect, useId, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({ startOnLoad: false, theme: "dark" });

export default function Mermaid({ chart, children }: { chart?: string; children?: string }) {
  const id = useId().replace(/:/g, "");
  const [svg, setSvg] = useState("");
  const src = (chart ?? (typeof children === "string" ? children : "")).trim();
  useEffect(() => {
    let live = true;
    mermaid
      .render(`m${id}`, src)
      .then((r) => {
        if (live) setSvg(r.svg);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [src, id]);
  return <div className="mermaid" dangerouslySetInnerHTML={{ __html: svg }} />;
}
