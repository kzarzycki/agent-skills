import { sources } from "virtual:mdx-docs";
import { Rendered } from "./mdxRender";

// Embed another doc's CURRENT content inline, rendered through the real MDX
// pipeline. Lets a page (e.g. a review/gate) show a live artifact without
// duplicating its text — point it at a canonical slug that always mirrors the
// latest version. `slug` is the doc filename without `.mdx` (e.g. "_spec-current").
export default function DocInclude({ slug }: { slug: string }) {
  const src = sources[slug];
  if (src == null) {
    return <div className="docdiff__err">DocInclude: source doc not found: {slug}</div>;
  }
  return (
    <div className="docinclude">
      <Rendered source={src} />
    </div>
  );
}
