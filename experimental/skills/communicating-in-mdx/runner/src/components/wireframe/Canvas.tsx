import type { ReactNode } from "react";

export function Canvas({ children }: { children?: ReactNode }) {
  return <div className="wf-canvas">{children}</div>;
}

export function Screen({
  name,
  title,
  width = 320,
  children,
}: {
  name: string;
  title?: string;
  width?: number;
  children?: ReactNode;
}) {
  return (
    <section className="wf-screen" style={{ width }}>
      <header className="wf-screen__bar">
        <span className="wf-screen__name">{name}</span>
        {title && <span className="wf-screen__title">{title}</span>}
      </header>
      <div className="wf-screen__body">{children}</div>
    </section>
  );
}
