import { useState } from "react";
import { serializeAnswers } from "../lib/copyback";

type Q = { id: string; label: string; type?: "text" | "choice"; options?: string[] };

export default function QuestionForm({ questions }: { questions: Q[] }) {
  const [ans, setAns] = useState<Record<string, string>>({});
  const [token, setToken] = useState("");
  const set = (id: string, v: string) => setAns((p) => ({ ...p, [id]: v }));
  const emit = () => {
    const t = serializeAnswers(ans);
    setToken(t);
    navigator.clipboard?.writeText(t).catch(() => {});
  };
  return (
    <form className="qform" onSubmit={(e) => e.preventDefault()}>
      {questions.map((q) => (
        <label key={q.id} className="qform__field">
          <span>{q.label}</span>
          {q.type === "choice" && q.options ? (
            <select aria-label={q.label} onChange={(e) => set(q.id, e.target.value)}>
              <option value="" />
              {q.options.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          ) : (
            <input aria-label={q.label} onChange={(e) => set(q.id, e.target.value)} />
          )}
        </label>
      ))}
      <button type="button" onClick={emit}>
        Copy answers
      </button>
      {token && (
        <textarea aria-label="answers token" className="qform__token" readOnly value={token} rows={6} />
      )}
    </form>
  );
}
