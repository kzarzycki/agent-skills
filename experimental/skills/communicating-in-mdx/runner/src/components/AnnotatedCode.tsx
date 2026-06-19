import { useEffect, useState } from "react";
import { getHighlighter } from "../lib/highlighter";

export default function AnnotatedCode({
  code,
  lang = "ts",
  notes = [],
}: {
  code: string;
  lang?: string;
  notes?: { line: number; text: string }[];
}) {
  const [html, setHtml] = useState("");
  useEffect(() => {
    let live = true;
    getHighlighter().then((h) => {
      if (live) setHtml(h.codeToHtml(code, { lang, theme: "github-dark" }));
    });
    return () => {
      live = false;
    };
  }, [code, lang]);
  return (
    <div className="annotated">
      <div className="annotated__code" dangerouslySetInnerHTML={{ __html: html }} />
      {notes.length > 0 && (
        <ul className="annotated__notes">
          {notes.map((n, i) => (
            <li key={i}>
              <b>L{n.line}</b> {n.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
