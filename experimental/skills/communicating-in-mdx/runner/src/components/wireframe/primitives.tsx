import type { ReactNode } from "react";

export const WBox = ({ children, h }: { children?: ReactNode; h?: number }) => (
  <div className="wf-box" style={h ? { minHeight: h } : undefined}>
    {children}
  </div>
);

export const WText = ({ lines = 1 }: { lines?: number }) => (
  <div className="wf-text">
    {Array.from({ length: lines }).map((_, i) => (
      <span key={i} className="wf-text__line" />
    ))}
  </div>
);

export const WButton = ({ children }: { children?: ReactNode }) => (
  <button className="wf-button" type="button">
    {children}
  </button>
);

export const WInput = ({ placeholder }: { placeholder?: string }) => (
  <div className="wf-input">{placeholder}</div>
);

export const WImage = ({ h = 80 }: { h?: number }) => (
  <div className="wf-image" style={{ minHeight: h }} aria-label="image placeholder" />
);

export const WRow = ({ children }: { children?: ReactNode }) => <div className="wf-row">{children}</div>;

export const WCol = ({ children }: { children?: ReactNode }) => <div className="wf-col">{children}</div>;
