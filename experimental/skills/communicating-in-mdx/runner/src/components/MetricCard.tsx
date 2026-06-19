export default function MetricCard({
  label,
  value,
  delta,
  tone = "info",
}: {
  label: string;
  value: string;
  delta?: string;
  tone?: "info" | "ok" | "warn" | "danger";
}) {
  return (
    <div className={`metric metric--${tone}`}>
      <span className="metric__label">{label}</span>
      <span className="metric__value">{value}</span>
      {delta && <span className="metric__delta">{delta}</span>}
    </div>
  );
}
