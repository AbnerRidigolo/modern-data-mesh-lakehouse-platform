interface MetricCardProps {
  label: string;
  value: string;
  delta?: string;
  deltaTone?: "positive" | "negative";
}

export default function MetricCard({ label, value, delta, deltaTone }: MetricCardProps) {
  return (
    <div className="metric-card">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {delta && <div className={`delta ${deltaTone ?? ""}`}>{delta}</div>}
    </div>
  );
}
