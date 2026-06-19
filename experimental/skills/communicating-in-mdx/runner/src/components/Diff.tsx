export default function Diff({ code }: { code: string }) {
  return (
    <pre className="diff">
      <code>
        {code.split("\n").map((line, i) => {
          const cls = line.startsWith("+")
            ? "diff__line--add"
            : line.startsWith("-")
              ? "diff__line--del"
              : "diff__line--ctx";
          return (
            <span key={i} className={`diff__line ${cls}`}>
              {line.replace(/^[+\- ]/, "")}
              {"\n"}
            </span>
          );
        })}
      </code>
    </pre>
  );
}
