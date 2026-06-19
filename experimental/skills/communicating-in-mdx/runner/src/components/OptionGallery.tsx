import { createContext, useContext, useState, type ReactNode } from "react";

type Selected = { name: string; label: string };
type Ctx = {
  selected: Selected | null;
  submitted: boolean;
  select: (name: string, label: string) => void;
};
const GalleryCtx = createContext<Ctx | null>(null);

export function OptionGallery({
  id,
  prompt,
  children,
}: {
  id?: string;
  prompt?: string;
  children?: ReactNode;
}) {
  const [selected, setSelected] = useState<Selected | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const select = (name: string, label: string) => {
    if (!submitted) setSelected({ name, label });
  };

  const submit = async () => {
    if (!selected) return;
    const form = id ?? (window.location.hash.slice(1) || "options");
    try {
      await fetch("/__mdx/answers", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ form, choice: selected.name, label: selected.label }),
      });
    } catch {
      // Offline: the selection still shows visually; nothing else to do.
    }
    setSubmitted(true);
  };

  return (
    <div className="gallery">
      {prompt && <p className="gallery__prompt">{prompt}</p>}
      <GalleryCtx.Provider value={{ selected, submitted, select }}>
        <div className="gallery__grid">{children}</div>
      </GalleryCtx.Provider>
      <div className="gallery__actions">
        <button
          type="button"
          className="gallery__submit"
          disabled={!selected || submitted}
          onClick={submit}
        >
          {submitted ? "Submitted ✓" : "Submit choice"}
        </button>
        {selected && !submitted && (
          <span className="gallery__pending">Selected: {selected.label}</span>
        )}
      </div>
      {submitted && selected && (
        <p className="gallery__chosen" role="status">
          ✓ Submitted “{selected.label}” — Claude can see it.
        </p>
      )}
    </div>
  );
}

export function Option({
  name,
  label,
  children,
}: {
  name: string;
  label?: string;
  children?: ReactNode;
}) {
  const ctx = useContext(GalleryCtx);
  const text = label ?? name;
  const active = ctx?.selected?.name === name;
  return (
    <figure className={`option${active ? " option--active" : ""}`}>
      <div className="option__preview">{children}</div>
      <figcaption className="option__cap">{text}</figcaption>
      <button
        type="button"
        className="option__btn"
        aria-pressed={active}
        disabled={ctx?.submitted}
        onClick={() => ctx?.select(name, text)}
      >
        {active ? "Selected ✓" : "Select"}
      </button>
    </figure>
  );
}
