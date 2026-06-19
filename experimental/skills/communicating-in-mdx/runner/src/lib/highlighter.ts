import { createHighlighter, type Highlighter } from "shiki";

let hl: Promise<Highlighter> | null = null;

export function getHighlighter() {
  if (!hl)
    hl = createHighlighter({
      themes: ["github-dark"],
      langs: ["ts", "tsx", "js", "json", "bash", "css", "html", "python"],
    });
  return hl;
}
