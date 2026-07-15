import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getDriftStatus, getPricingMetadata, simulatePricing } from "../api/endpoints";
import Alert from "../components/Alert";
import MetricCard from "../components/MetricCard";
import type { SimulationResult } from "../api/types";

const currency = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function MLOpsPage() {
  const { data: metadata, isError: metadataError } = useQuery({
    queryKey: ["pricing-metadata"],
    queryFn: getPricingMetadata,
    retry: false,
  });
  const { data: drift } = useQuery({ queryKey: ["drift-status"], queryFn: getDriftStatus, retry: false });

  const products = useMemo(() => (metadata ? Object.keys(metadata.optimal_prices) : []), [metadata]);
  const [selectedProduct, setSelectedProduct] = useState("");
  const [simPrice, setSimPrice] = useState(0);
  const [isWeekend, setIsWeekend] = useState(false);
  const [simResult, setSimResult] = useState<SimulationResult | null>(null);
  const [curve, setCurve] = useState<{ price: number; demand: number; revenue: number }[]>([]);
  const [curveLoading, setCurveLoading] = useState(false);

  useEffect(() => {
    if (!selectedProduct && products.length > 0) {
      setSelectedProduct(products[0]);
    }
  }, [products, selectedProduct]);

  const details = metadata && selectedProduct ? metadata.optimal_prices[selectedProduct] : undefined;

  useEffect(() => {
    if (details) {
      setSimPrice(details.base_price);
      setCurve([]);
      setSimResult(null);
    }
  }, [details, selectedProduct]);

  async function runSimulation(price: number) {
    if (!selectedProduct) return;
    const result = await simulatePricing(selectedProduct, price, isWeekend);
    setSimResult(result);
  }

  async function generateCurve() {
    if (!details || !selectedProduct) return;
    setCurveLoading(true);
    try {
      const min = Math.max(10, details.base_price * 0.4);
      const max = details.base_price * 1.6;
      const step = (max - min) / 12;
      const prices = Array.from({ length: 13 }, (_, i) => min + i * step);
      const results = await Promise.all(prices.map((p) => simulatePricing(selectedProduct, p, isWeekend)));
      setCurve(results.map((r) => ({ price: r.simulated_price, demand: r.projected_demand, revenue: r.projected_revenue })));
    } finally {
      setCurveLoading(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>📈 Otimização de Elasticidade e Precificação Dinâmica</h2>
        <p>
          Modelo de Machine Learning (Random Forest Regressor) treinado no Lakehouse, simulando resposta de demanda e
          calculando o preço ideal de maximização de faturamento.
        </p>
      </div>

      {metadataError && (
        <Alert kind="warning">O modelo de ML e os metadados de otimização ainda não foram gerados. Execute a DAG do Airflow.</Alert>
      )}

      {drift && (
        <Alert kind={drift.overall_drift_detected ? "error" : "success"}>
          {drift.overall_drift_detected
            ? "🚨 Alerta de Drift: desvio estatístico significativo detectado nos preços recentes. Recomenda-se retreinar o pipeline."
            : "✅ Drift Monitor: distribuições de preços recentes estão estáveis e em conformidade com os dados de treino."}
        </Alert>
      )}

      {metadata && (
        <>
          <div className="card">
            <div className="metric-grid mb-0">
              <MetricCard label="Acurácia do Modelo (Test R²)" value={`${(metadata.model_metrics.r2_score * 100).toFixed(2)}%`} />
              <MetricCard label="Erro Médio Absoluto (MAE)" value={`${metadata.model_metrics.mae.toFixed(2)} unidades`} />
              <MetricCard label="Último Retreino" value={new Date(metadata.last_trained).toLocaleString("pt-BR")} />
            </div>
          </div>

          <div className="card">
            <p className="card-title">Escolha um produto</p>
            <select className="select" value={selectedProduct} onChange={(e) => setSelectedProduct(e.target.value)}>
              {products.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>

            {details && (
              <div className="metric-grid mt-16 mb-0">
                <MetricCard label="Preço Praticado Atual" value={currency(details.base_price)} />
                <MetricCard
                  label="Preço Ótimo Sugerido (P*)"
                  value={currency(details.optimal_price)}
                  delta={currency(details.optimal_price - details.base_price)}
                  deltaTone={details.optimal_price >= details.base_price ? "positive" : "negative"}
                />
                <MetricCard label="Preço Médio Concorrente" value={currency(details.competitor_price)} />
                <MetricCard label="Lift Estimado de Faturamento" value={`+${details.revenue_lift_pct.toFixed(2)}%`} />
              </div>
            )}
          </div>

          {details && (
            <div className="card">
              <p className="card-title">🎮 Simulador de Preço e Demanda Interativo</p>
              <input
                type="range"
                min={Math.max(10, details.base_price * 0.4)}
                max={details.base_price * 1.6}
                step={5}
                value={simPrice}
                onChange={(e) => setSimPrice(Number(e.target.value))}
                onMouseUp={() => runSimulation(simPrice)}
                onTouchEnd={() => runSimulation(simPrice)}
                style={{ width: "100%" }}
              />
              <p className="text-muted">Preço simulado: {currency(simPrice)}</p>

              <label className="flex items-center gap-12">
                <input
                  type="checkbox"
                  checked={isWeekend}
                  onChange={(e) => {
                    setIsWeekend(e.target.checked);
                    runSimulation(simPrice);
                  }}
                />
                Simular vendas no fim de semana?
              </label>

              <button type="button" className="btn mt-16" onClick={() => runSimulation(simPrice)}>
                Simular
              </button>

              {simResult && (
                <div className="metric-grid mt-16 mb-0">
                  <MetricCard label="Demanda Diária Projetada" value={`${simResult.projected_demand.toFixed(2)} unidades`} />
                  <MetricCard label="Faturamento Diário Projetado" value={currency(simResult.projected_revenue)} />
                  <MetricCard
                    label="Lift Comparado ao Baseline"
                    value={`${simResult.lift_vs_baseline_pct >= 0 ? "+" : ""}${simResult.lift_vs_baseline_pct.toFixed(2)}%`}
                    deltaTone={simResult.lift_vs_baseline_pct >= 0 ? "positive" : "negative"}
                  />
                </div>
              )}

              <button type="button" className="btn secondary mt-16" onClick={generateCurve} disabled={curveLoading}>
                {curveLoading ? "Gerando curvas..." : "📊 Gerar Curvas de Elasticidade"}
              </button>

              {curve.length > 0 && (
                <div className="metric-grid mt-16" style={{ gridTemplateColumns: "1fr 1fr" }}>
                  <div style={{ height: 240 }}>
                    <p className="text-muted">📉 Curva de Demanda</p>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={curve}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                        <XAxis dataKey="price" stroke="#94a3b8" fontSize={11} tickFormatter={(v) => v.toFixed(0)} />
                        <YAxis stroke="#94a3b8" fontSize={11} />
                        <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                        <Line type="monotone" dataKey="demand" stroke="#ef4444" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <div style={{ height: 240 }}>
                    <p className="text-muted">💰 Curva de Receita</p>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={curve}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                        <XAxis dataKey="price" stroke="#94a3b8" fontSize={11} tickFormatter={(v) => v.toFixed(0)} />
                        <YAxis stroke="#94a3b8" fontSize={11} />
                        <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                        <Line type="monotone" dataKey="revenue" stroke="#10b981" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
