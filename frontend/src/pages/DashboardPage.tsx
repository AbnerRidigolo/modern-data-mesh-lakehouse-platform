import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { clearCache, getKpis } from "../api/endpoints";
import Alert from "../components/Alert";
import MetricCard from "../components/MetricCard";

const currency = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function DashboardPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["kpis"],
    queryFn: getKpis,
    retry: false,
  });

  const [latency, setLatency] = useState<{ label: string; seconds: number } | null>(null);
  const [busy, setBusy] = useState(false);

  async function measureWithoutCache() {
    setBusy(true);
    try {
      await clearCache();
      const start = performance.now();
      await getKpis();
      setLatency({ label: "Cache Miss (DB)", seconds: (performance.now() - start) / 1000 });
      refetch();
    } finally {
      setBusy(false);
    }
  }

  async function measureWithCache() {
    setBusy(true);
    try {
      const start = performance.now();
      await getKpis();
      setLatency({ label: "Cache Hit (Redis)", seconds: (performance.now() - start) / 1000 });
    } finally {
      setBusy(false);
    }
  }

  const kpis = data?.data ?? [];
  const latest = kpis[0];

  return (
    <div>
      <div className="page-header">
        <h2>Dashboard de Performance &amp; KPIs Financeiros</h2>
        <p>Métricas consolidadas do Data Warehouse, servidas via FastAPI com cache Redis.</p>
      </div>

      <div className="card">
        <p className="card-title">Simulação de Latência &amp; Caching</p>
        <div className="flex gap-12">
          <button type="button" className="btn secondary" onClick={measureWithoutCache} disabled={busy}>
            Consultar API (Sem Cache / Forçar DB)
          </button>
          <button type="button" className="btn" onClick={measureWithCache} disabled={busy}>
            Consultar API (Com Cache / Redis)
          </button>
        </div>
        {latency && (
          <div className="mt-16">
            <MetricCard label={latency.label} value={`${latency.seconds.toFixed(4)}s`} />
          </div>
        )}
      </div>

      {isLoading && <Alert kind="info">Carregando KPIs...</Alert>}
      {isError && <Alert kind="warning">FastAPI Gateway offline ou pipeline ainda não executada. Não é possível renderizar os gráficos dinâmicos.</Alert>}

      {!isLoading && !isError && kpis.length === 0 && (
        <Alert kind="warning">Nenhum dado KPI disponível. Execute o pipeline no Airflow primeiro.</Alert>
      )}

      {latest && (
        <div className="card">
          <p className="card-title">KPIs Consolidados por Mês</p>
          <div className="metric-grid mb-0">
            <MetricCard label="Mês" value={String(latest.sales_month)} />
            <MetricCard label="Faturamento Líquido" value={currency(latest.net_revenue)} />
            <MetricCard label="Pedidos Concluídos" value={String(latest.completed_orders_count)} />
            <MetricCard label="Ticket Médio" value={currency(latest.average_ticket)} />
          </div>

          <div className="mt-16" style={{ height: 280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={[...kpis].reverse()}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="sales_month" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                <Bar dataKey="net_revenue" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="table-scroll mt-16">
            <table className="data-table">
              <thead>
                <tr>
                  {Object.keys(kpis[0]).map((col) => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {kpis.map((row, idx) => (
                  <tr key={idx}>
                    {Object.keys(kpis[0]).map((col) => (
                      <td key={col}>{String(row[col])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
