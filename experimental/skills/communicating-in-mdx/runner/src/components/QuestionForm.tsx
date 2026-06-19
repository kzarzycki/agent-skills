import { useState } from "react";
import { serializeAnswers } from "../lib/copyback";

type Q = { id: string; label: string; type?: "text" | "choice"; options?: string[] };

export default function QuestionForm({ questions, id }: { questions: Q[]; id?: string }) {
  const [ans, setAns] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"idle" | "sent" | "fallback">("idle");
  const [token, setToken] = useState("");
  const set = (qid: string, v: string) => setAns((p) => ({ ...p, [qid]: v }));

  const submit = async () => {
    const form = id ?? (window.location.hash.slice(1) || "form");
    try {
      const r = await fetch("/__mdx/answers", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ form, answers: ans }),
      });
      if (!r.ok) throw new Error(`status ${r.status}`);
      setStatus("sent");
    } catch {
      // No runner endpoint (e.g. opened as a static file). Fall back to the
      // copy-paste token so answers can still reach the agent.
      setToken(serializeAnswers(ans));
      setStatus("fallback");
    }
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
      <button type="button" onClick={submit}>
        Submit answers
      </button>
      {status === "sent" && (
        <p className="qform__sent" role="status">
          ✓ Submitted — Claude can see your answers.
        </p>
      )}
      {status === "fallback" && (
        <>
          <p className="qform__hint" role="status">
            No live runner — copy this token into chat:
          </p>
          <textarea aria-label="answers token" className="qform__token" readOnly value={token} rows={6} />
        </>
      )}
    </form>
  );
}
