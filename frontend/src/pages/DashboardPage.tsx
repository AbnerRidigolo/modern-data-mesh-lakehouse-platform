import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getCategoryPerformance, getDailyRevenue, getKpis } from "../api/endpoints";
import Alert from "../components/Alert";
import Sparkline from "../components/Sparkline";
import type { CategoryPerformance, DailyRevenuePoint, MonthlyKpi } from "../api/types";

const currency = (v: number) =>
  `R$ ${Number(v ?? 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const compactCurrency = (v: number) =>
  `R$ ${Number(v ?? 0).toLocaleString("pt-BR", { notation: "compact", maximumFractionDigits: 1 })}`;
const integer = (v: number) => Number(v ?? 0).toLocaleString("pt-BR");
const pct = (v: number) => `${Number(v ?? 0).toFixed(1)}%`;

const CATEGORY_COLORS = ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ec4899", "#06b6d4"];
const PERIODS = [
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
  { label: "180d", days: 180 },
  { label: "12m", days: 365 },
];

function deltaTone(v: number): "positive" | "negative" | "" {
  if (v > 0.05) return "positive";
  if (v < -0.05) return "negative";
  return "";
}

function formatShortDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

interface HeroKpi {
  label: string;
  value: string;
  deltaPct: number | null;
  spark: number[];
  color: string;
}

export default function DashboardPage() {
  const [days, setDays] = useState(90);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const kpisQ = useQuery({ queryKey: ["kpis"], queryFn: getKpis, retry: false });
  const dailyQ = useQuery({
    queryKey: ["daily-revenue", days],
    queryFn: () => getDailyRevenue(days),
    retry: false,
  });
  const catQ = useQuery({ queryKey: ["category-performance"], queryFn: getCategoryPerformance, retry: false });

  const monthlyKpis: MonthlyKpi[] = kpisQ.data?.data ?? [];
  const daily: DailyRevenuePoint[] = dailyQ.data?.data ?? [];
  const categories: CategoryPerformance[] = catQ.data?.data ?? [];

  const heroes = useMemo<HeroKpi[]>(() => {
    // MoM: dm_monthly_kpis vem em ordem desc (mês mais recente primeiro)
    const current = monthlyKpis[0];
    const prev = monthlyKpis[1];
    const momDelta = (cur?: number, old?: number) =>
      cur !== undefined && old !== undefined && old !== 0 ? (cur - old) / old : null;

    const revSpark = daily.map((d) => d.net_revenue);
    const ordersSpark = daily.map((d) => d.orders);
    const custSpark = daily.map((d) => d.active_customers);
    const ticketSpark = daily.map((d) => (d.orders ? d.net_revenue / d.orders : 0));

    return [
      {
        label: "Faturamento (mês atual)",
        value: current ? currency(current.net_revenue) : "—",
        deltaPct: momDelta(current?.net_revenue, prev?.net_revenue),
        spark: revSpark,
        color: "#3b82f6",
      },
      {
        label: "Pedidos Concluídos",
        value: current ? integer(current.completed_orders_count) : "—",
        deltaPct: momDelta(current?.completed_orders_count, prev?.completed_orders_count),
        spark: ordersSpark,
        color: "#10b981",
      },
      {
        label: "Ticket Médio",
        value: current ? currency(current.average_ticket) : "—",
        deltaPct: momDelta(current?.average_ticket, prev?.average_ticket),
        spark: ticketSpark,
        color: "#8b5cf6",
      },
      {
        label: "Clientes Ativos (período)",
        value: integer(daily.reduce((acc, d) => Math.max(acc, d.active_customers), 0)),
        deltaPct: null,
        spark: custSpark,
        color: "#f59e0b",
      },
    ];
  }, [monthlyKpis, daily]);

  const chartData = useMemo(
    () =>
      daily.map((d) => ({
        date: formatShortDate(d.revenue_date),
        Receita: d.net_revenue,
        "Média 7d": d.revenue_7d_avg,
      })),
    [daily],
  );

  const drillCategory = activeCategory ? categories.find((c) => c.category === activeCategory) : null;

  const anyLoading = kpisQ.isLoading || dailyQ.isLoading || catQ.isLoading;
  const allError = kpisQ.isError && dailyQ.isError && catQ.isError;

  return (
    <div>
      <div className="page-header flex items-center justify-between">
        <div>
          <h2>Executive Dashboard — Revenue Intelligence</h2>
          <p>
            Camada semântica (dbt marts) servida via FastAPI com cache Redis. Tendência diária, drill-down por
            categoria e KPIs financeiros consolidados do Data Warehouse.
          </p>
        </div>
        <div className="period-toggle">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              type="button"
              className={`period-btn${days === p.days ? " active" : ""}`}
              onClick={() => setDays(p.days)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {allError && (
        <Alert kind="warning">
          FastAPI Gateway offline ou pipeline ainda não executada. Execute o DAG no Airflow para materializar os marts.
        </Alert>
      )}

      <div className="hero-grid">
        {heroes.map((h) => (
          <div key={h.label} className="hero-card">
            <div className="hero-top">
              <span className="hero-label">{h.label}</span>
              {h.deltaPct !== null && (
                <span className={`hero-delta ${deltaTone(h.deltaPct)}`}>
                  {h.deltaPct > 0 ? "▲" : h.deltaPct < 0 ? "▼" : "▬"} {pct(Math.abs(h.deltaPct) * 100)}
                  <em> MoM</em>
                </span>
              )}
            </div>
            <div className="hero-value">{h.value}</div>
            <div className="hero-spark">
              <Sparkline values={h.spark} color={h.color} width={220} height={40} />
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="flex items-center justify-between">
          <p className="card-title mb-0">Tendência de Receita Diária &amp; Média Móvel 7 dias</p>
          {anyLoading && <span className="text-muted" style={{ fontSize: 12 }}>carregando…</span>}
        </div>
        <div className="mt-16" style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
              <defs>
                <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickMargin={8} minTickGap={24} />
              <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => compactCurrency(v)} width={64} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }}
                formatter={(v) => currency(Number(v))}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Receita" fill="url(#revGrad)" stroke="#3b82f6" radius={[3, 3, 0, 0]} maxBarSize={22} />
              <Line
                type="monotone"
                dataKey="Média 7d"
                stroke="#f59e0b"
                strokeWidth={2.4}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="split-grid">
        <div className="card">
          <p className="card-title">Receita por Categoria — clique para drill-down</p>
          {categories.length === 0 && !catQ.isLoading && (
            <p className="text-muted" style={{ fontSize: 13 }}>Sem dados de categoria.</p>
          )}
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={categories} layout="vertical" margin={{ left: 12, right: 24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                <XAxis type="number" stroke="#64748b" fontSize={11} tickFormatter={(v) => compactCurrency(v)} />
                <YAxis
                  type="category"
                  dataKey="category"
                  stroke="#94a3b8"
                  fontSize={12}
                  width={92}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: "rgba(148,163,184,0.06)" }}
                  contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }}
                  formatter={(v) => currency(Number(v))}
                />
                <Bar
                  dataKey="net_revenue"
                  radius={[0, 4, 4, 0]}
                  maxBarSize={30}
                  onClick={(d) => {
                    const cat = (d as { category?: string }).category ?? null;
                    setActiveCategory((prev) => (prev === cat ? null : cat));
                  }}
                >
                  {categories.map((c, i) => (
                    <Cell
                      key={c.category}
                      cursor="pointer"
                      fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                      fillOpacity={activeCategory && activeCategory !== c.category ? 0.35 : 1}
                    />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <p className="card-title">{drillCategory ? `Drill-down: ${drillCategory.category}` : "Mix de Categorias"}</p>
          {drillCategory ? (
            <div className="drill-panel">
              <div className="metric-grid mb-0">
                <div className="metric-card">
                  <div className="label">Faturamento</div>
                  <div className="value">{currency(drillCategory.net_revenue)}</div>
                  <div className="delta">{pct(drillCategory.revenue_share_pct)} do total</div>
                </div>
                <div className="metric-card">
                  <div className="label">Pedidos</div>
                  <div className="value">{integer(drillCategory.orders)}</div>
                </div>
                <div className="metric-card">
                  <div className="label">Ticket Médio</div>
                  <div className="value">{currency(drillCategory.average_ticket)}</div>
                </div>
                <div className="metric-card">
                  <div className="label">Clientes Únicos</div>
                  <div className="value">{integer(drillCategory.unique_customers)}</div>
                </div>
              </div>
              <button type="button" className="btn secondary mt-16" onClick={() => setActiveCategory(null)}>
                Limpar seleção
              </button>
            </div>
          ) : (
            <div className="mix-list">
              {categories.map((c, i) => (
                <button
                  type="button"
                  key={c.category}
                  className="mix-row"
                  onClick={() => setActiveCategory(c.category)}
                >
                  <span className="mix-dot" style={{ background: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }} />
                  <span className="mix-name">{c.category}</span>
                  <span className="mix-bar-track">
                    <span
                      className="mix-bar-fill"
                      style={{
                        width: `${c.revenue_share_pct}%`,
                        background: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                      }}
                    />
                  </span>
                  <span className="mix-pct">{pct(c.revenue_share_pct)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
