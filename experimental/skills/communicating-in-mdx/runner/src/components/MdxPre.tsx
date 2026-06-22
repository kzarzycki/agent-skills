import Mermaid from "./Mermaid";

// MDX compiles a ```mermaid fenced block to <pre><code class="language-mermaid">…</code></pre>.
// Overriding the `pre` element lets a mermaid fence render as a real diagram while
// every other fenced/code block falls through to a normal <pre>. This keeps
// ```mermaid portable in plain markdown (GitHub etc. render it too) instead of
// needing an MDX-only <Mermaid> tag in the document.
//
// Only markdown-generated code blocks pass through here; literal <pre> rendered
// by other components (Diff, AnnotatedCode) are real intrinsics and unaffected.
export default function Pre(props: any) {
  const codeProps = props?.children?.props;
  const className: string = codeProps?.className ?? "";
  const raw = codeProps?.children;
  if (/(^|\s)language-mermaid(\s|$)/.test(className) && typeof raw === "string") {
    return <Mermaid chart={raw} />;
  }
  return <pre {...props} />;
}
