import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getMarketingPerformance } from "../api/endpoints";
import Alert from "../components/Alert";
import type { MarketingPerformance } from "../api/types";

const currency = (v: number) =>
  `R$ ${Number(v ?? 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const compact = (v: number) => Number(v ?? 0).toLocaleString("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const num = (v: number, d = 2) => Number(v ?? 0).toFixed(d);

const CATEGORIES = ["Todos", "Áudio", "Periféricos", "Acessórios", "Educação"];

function roasTone(roas: number | null): "positive" | "negative" | "" {
  if (roas === null) return "";
  if (roas >= 1) return "positive";
  return "negative";
}

function monthLabel(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { month: "short", year: "2-digit" });
}

export default function MarketingPage() {
  const [category, setCategory] = useState<string>("Todos");
  const filter = category === "Todos" ? undefined : category;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["marketing", category],
    queryFn: () => getMarketingPerformance(filter),
    retry: false,
  });

  const rows: MarketingPerformance[] = data?.data ?? [];

  const totals = useMemo(() => {
    const spend = rows.reduce((a, r) => a + (r.spend ?? 0), 0);
    const revenue = rows.reduce((a, r) => a + (r.attributed_revenue ?? 0), 0);
    const clicks = rows.reduce((a, r) => a + (r.clicks ?? 0), 0);
    const impressions = rows.reduce((a, r) => a + (r.impressions ?? 0), 0);
    const buyers = rows.reduce((a, r) => a + (r.buyers ?? 0), 0);
    return {
      spend,
      revenue,
      roas: spend ? revenue / spend : 0,
      ctr: impressions ? (clicks / impressions) * 100 : 0,
      cac: buyers ? spend / buyers : 0,
      clicks,
      impressions,
    };
  }, [rows]);

  // funil agregado: impressões → cliques → pedidos → compradores
  const funnel = useMemo(() => {
    const impressions = rows.reduce((a, r) => a + (r.impressions ?? 0), 0);
    const clicks = rows.reduce((a, r) => a + (r.clicks ?? 0), 0);
    const orders = rows.reduce((a, r) => a + (r.orders ?? 0), 0);
    const buyers = rows.reduce((a, r) => a + (r.buyers ?? 0), 0);
    const stages = [
      { stage: "Impressões", value: impressions, color: "#3b82f6" },
      { stage: "Cliques", value: clicks, color: "#06b6d4" },
      { stage: "Pedidos", value: orders, color: "#8b5cf6" },
      { stage: "Compradores", value: buyers, color: "#10b981" },
    ];
    const top = impressions || 1;
    return stages.map((s) => ({ ...s, widthPct: Math.max(2, (s.value / top) * 100) }));
  }, [rows]);

  // ROAS por mês para o gráfico
  const roasByMonth = useMemo(() => {
    const byMonth = new Map<string, { spend: number; revenue: number }>();
    for (const r of rows) {
      const key = r.activity_month;
      const cur = byMonth.get(key) ?? { spend: 0, revenue: 0 };
      cur.spend += r.spend ?? 0;
      cur.revenue += r.attributed_revenue ?? 0;
      byMonth.set(key, cur);
    }
    return [...byMonth.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([month, v]) => ({ month: monthLabel(month), roas: v.spend ? +(v.revenue / v.spend).toFixed(2) : 0 }));
  }, [rows]);

  return (
    <div>
      <div className="page-header flex items-center justify-between">
        <div>
          <h2>Marketing Performance — Growth &amp; Mídia Paga</h2>
          <p>
            Domínio Marketing do Data Mesh cruzado com receita atribuída. Eficiência de mídia (ROAS, CAC, CTR, CPC)
            por mês e categoria, com funil de conversão de impressão a compra.
          </p>
        </div>
        <div className="period-toggle">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              className={`period-btn${category === c ? " active" : ""}`}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {isError && (
        <Alert kind="warning">
          FastAPI Gateway offline ou marts de marketing ainda não materializados. Execute o DAG no Airflow.
        </Alert>
      )}
      {isLoading && <Alert kind="info">Carregando performance de marketing…</Alert>}

      <div className="hero-grid">
        <div className="hero-card">
          <div className="hero-top">
            <span className="hero-label">Investimento em Mídia</span>
          </div>
          <div className="hero-value">{currency(totals.spend)}</div>
        </div>
        <div className="hero-card">
          <div className="hero-top">
            <span className="hero-label">Receita Atribuída</span>
          </div>
          <div className="hero-value">{currency(totals.revenue)}</div>
        </div>
        <div className="hero-card">
          <div className="hero-top">
            <span className="hero-label">ROAS (retorno / R$)</span>
            <span className={`hero-delta ${roasTone(totals.roas)}`}>
              {totals.roas >= 1 ? "lucro" : "prejuízo"}
            </span>
          </div>
          <div className="hero-value">{num(totals.roas)}x</div>
        </div>
        <div className="hero-card">
          <div className="hero-top">
            <span className="hero-label">CAC médio</span>
          </div>
          <div className="hero-value">{currency(totals.cac)}</div>
        </div>
      </div>

      <div className="split-grid">
        <div className="card">
          <p className="card-title">Funil de Conversão (agregado do período)</p>
          <div className="funnel">
            {funnel.map((s, i) => {
              const prev = i > 0 ? funnel[i - 1].value : s.value;
              const convRate = prev ? (s.value / prev) * 100 : 100;
              return (
                <div key={s.stage} className="funnel-row">
                  <div className="funnel-head">
                    <span>{s.stage}</span>
                    <span className="text-muted">{compact(s.value)}{i > 0 && ` · ${convRate.toFixed(1)}%`}</span>
                  </div>
                  <div className="funnel-bar-track">
                    <div className="funnel-bar-fill" style={{ width: `${s.widthPct}%`, background: s.color }} />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="metric-grid mt-16">
            <div className="metric-card">
              <div className="label">CTR médio</div>
              <div className="value">{num(totals.ctr)}%</div>
            </div>
            <div className="metric-card">
              <div className="label">Impressões</div>
              <div className="value">{compact(totals.impressions)}</div>
            </div>
          </div>
        </div>

        <div className="card">
          <p className="card-title">ROAS por Mês</p>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={roasByMonth} margin={{ top: 8, right: 12, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="month" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip
                  contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }}
                  formatter={(v) => `${Number(v)}x`}
                />
                <Bar dataKey="roas" radius={[4, 4, 0, 0]} maxBarSize={40}>
                  {roasByMonth.map((r) => (
                    <Cell key={r.month} fill={r.roas >= 1 ? "#10b981" : "#ef4444"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <p className="card-title">Detalhamento por Mês × Categoria</p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Mês</th>
                <th>Categoria</th>
                <th>Investimento</th>
                <th>Impressões</th>
                <th>Cliques</th>
                <th>CTR</th>
                <th>CPC</th>
                <th>Receita Atrib.</th>
                <th>ROAS</th>
                <th>CAC</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => (
                <tr key={`${r.activity_month}-${r.category}-${idx}`}>
                  <td>{monthLabel(r.activity_month)}</td>
                  <td>{r.category}</td>
                  <td>{currency(r.spend)}</td>
                  <td>{compact(r.impressions)}</td>
                  <td>{compact(r.clicks)}</td>
                  <td>{num(r.ctr_pct)}%</td>
                  <td>{currency(r.cpc)}</td>
                  <td>{currency(r.attributed_revenue)}</td>
                  <td>
                    <span className={`badge ${roasTone(r.roas) === "positive" ? "pass" : "fail"}`}>
                      {r.roas === null ? "—" : `${num(r.roas)}x`}
                    </span>
                  </td>
                  <td>{r.cac === null ? "—" : currency(r.cac)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
