import { Suspense, lazy, useMemo, useSyncExternalStore } from "react";
import { loadDocs } from "./docs";

function useHash() {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener("hashchange", cb);
      return () => window.removeEventListener("hashchange", cb);
    },
    () => window.location.hash.slice(1),
  );
}

export default function App() {
  const docs = useMemo(() => loadDocs(), []);
  const slug = useHash();
  const current = docs.find((d) => d.slug === slug);

  if (docs.length === 0)
    return (
      <main className="app">
        <p className="app__empty">No .mdx documents found in this directory.</p>
      </main>
    );

  return (
    <div className="layout">
      <nav className="sidebar">
        <h2 className="sidebar__title">Documents</h2>
        <ul>
          {docs.map((d) => (
            <li key={d.slug}>
              <a href={`#${d.slug}`} className={d.slug === slug ? "active" : ""}>
                {d.title}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <main className="app">
        {current ? <DocView entry={current} /> : <p className="app__empty">Select a document.</p>}
      </main>
    </div>
  );
}

function DocView({ entry }: { entry: ReturnType<typeof loadDocs>[number] }) {
  const Doc = useMemo(() => lazy(entry.load), [entry.slug]);
  return (
    <article className="doc">
      <Suspense fallback={<p>Loading…</p>}>
        <Doc />
      </Suspense>
    </article>
  );
}
