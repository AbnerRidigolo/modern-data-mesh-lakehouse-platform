import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getSearchLogs, searchProducts, simulatePricing } from "../api/endpoints";
import Alert from "../components/Alert";
import MetricCard from "../components/MetricCard";
import type { SearchResultItem, SimulationResult } from "../api/types";

const currency = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const SUGGESTIONS = [
  "🎧 Fone sem fio cancelamento ruído",
  "⌨️ Teclado confortável com switch brown",
  "📚 Aprender modelagem dbt e airflow",
  "🖥️ Tela ultrawide para programar",
];

function ProductSimulator({ product }: { product: SearchResultItem }) {
  const [price, setPrice] = useState(product.pricing_details?.base_price ?? 0);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const base = product.pricing_details?.base_price ?? 0;

  async function simulate(nextPrice: number) {
    setPrice(nextPrice);
    try {
      const res = await simulatePricing(product.name, nextPrice, false);
      setResult(res);
    } catch {
      setResult(null);
    }
  }

  return (
    <details className="mt-16">
      <summary className="text-muted" style={{ cursor: "pointer" }}>
        🎮 Ajustar Preço e Simular Demanda
      </summary>
      <div className="mt-16">
        <input
          type="range"
          min={base * 0.5}
          max={base * 1.5}
          step={5}
          value={price}
          onChange={(e) => simulate(Number(e.target.value))}
          style={{ width: "100%" }}
        />
        <p className="text-muted">Preço simulado: {currency(price)}</p>
        {result && (
          <p>
            📈 Demanda projetada: {result.projected_demand.toFixed(2)} unidades/dia
            <br />
            💰 Faturamento projetado: {currency(result.projected_revenue)}/dia
          </p>
        )}
      </div>
    </details>
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [gapThreshold, setGapThreshold] = useState(0.6);

  const { data: logs } = useQuery({ queryKey: ["search-logs"], queryFn: () => getSearchLogs(50) });

  const { data: results, isFetching } = useQuery({
    queryKey: ["search", query],
    queryFn: () => searchProducts(query),
    enabled: query.length > 0,
    retry: false,
  });

  const totalSearches = logs?.length ?? 0;
  const cacheHits = logs?.filter((l) => l.source === "cache").length ?? 0;
  const hitRate = totalSearches > 0 ? (cacheHits / totalSearches) * 100 : 0;
  const avgLatency = totalSearches > 0 ? logs!.reduce((sum, l) => sum + l.latency_seconds, 0) / totalSearches : 0;
  const gapQueries = logs?.filter((l) => l.top_score < gapThreshold) ?? [];

  return (
    <div>
      <div className="page-header">
        <h2>🔍 Busca Semântica Vetorial de Produtos</h2>
        <p>
          Embeddings densos gerados pelo modelo FastEmbed (BGE), pesquisados por similaridade de cosseno no banco de
          dados vetorial Qdrant.
        </p>
      </div>

      <details className="card">
        <summary className="card-title" style={{ cursor: "pointer" }}>
          📊 Observabilidade &amp; Search Analytics (Real-Time)
        </summary>
        <div className="metric-grid mt-16 mb-0">
          <MetricCard label="Total de Buscas" value={String(totalSearches)} />
          <MetricCard label="Taxa de Cache Hit (Redis)" value={`${hitRate.toFixed(1)}%`} delta={`${cacheHits} acertos`} deltaTone="positive" />
          <MetricCard label="Latência Média" value={`${avgLatency.toFixed(4)}s`} />
        </div>

        <p className="card-title mt-16">⚠️ Catalog Gaps (Buscas sem correspondência ideal)</p>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={gapThreshold}
          onChange={(e) => setGapThreshold(Number(e.target.value))}
          style={{ width: "100%" }}
        />
        <p className="text-muted">Limite de similaridade mínima: {(gapThreshold * 100).toFixed(0)}%</p>

        {gapQueries.length === 0 ? (
          <Alert kind="success">✅ Todas as buscas recentes tiveram correspondência acima do limite.</Alert>
        ) : (
          <>
            <Alert kind="warning">{gapQueries.length} buscas com similaridade abaixo de {(gapThreshold * 100).toFixed(0)}%.</Alert>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Query</th>
                    <th>Top Match</th>
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {gapQueries.map((g, idx) => (
                    <tr key={idx}>
                      <td>{g.timestamp}</td>
                      <td>{g.query}</td>
                      <td>{g.top_match}</td>
                      <td>{g.top_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </details>

      <p className="text-muted mt-16">💡 Buscas Sugeridas:</p>
      <div className="suggestion-row">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="suggestion-chip" onClick={() => setQuery(s.replace(/^\S+\s/, ""))}>
            {s}
          </button>
        ))}
      </div>

      <input
        className="input"
        placeholder="Ex: dispositivo ergonômico para evitar dores no pulso..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      {isFetching && <Alert kind="info">Buscando...</Alert>}

      {results && (
        <div className="mt-16">
          <div className="metric-grid mb-0">
            <MetricCard label="Tempo Total da Requisição" value={`${(results.query_time_seconds ?? 0).toFixed(4)}s`} />
            <MetricCard label="Origem da Resposta" value={results.source === "cache" ? "Cache (Redis)" : "Banco Vetorial (Qdrant)"} />
          </div>

          {results.data.length === 0 ? (
            <Alert kind="warning" >
              Nenhum produto correspondente encontrado. Certifique-se de que a DAG de indexação foi executada.
            </Alert>
          ) : (
            results.data.map((product) => (
              <div className="product-card" key={product.id}>
                <div className="flex justify-between items-center">
                  <h3 style={{ margin: 0 }}>{product.name}</h3>
                  <span className="badge pass">{product.category}</span>
                </div>
                <p className="text-muted">{product.description}</p>
                <div className="flex justify-between">
                  <span className="text-muted">Score de Similaridade Semântica</span>
                  <span style={{ color: "var(--accent-green)", fontWeight: 700 }}>{Math.round(product.score * 100)}%</span>
                </div>
                <div className="similarity-bar">
                  <div className="similarity-bar-fill" style={{ width: `${Math.round(product.score * 100)}%` }} />
                </div>

                {product.pricing_details ? (
                  <>
                    <div className="metric-grid mt-16 mb-0">
                      <MetricCard label="Preço Praticado" value={currency(product.pricing_details.base_price)} />
                      <MetricCard label="Preço Ótimo (P*)" value={currency(product.pricing_details.optimal_price)} />
                      <MetricCard label="Lift de Faturamento" value={`+${product.pricing_details.revenue_lift_pct.toFixed(2)}%`} />
                    </div>
                    <ProductSimulator product={product} />
                  </>
                ) : (
                  <Alert kind="info">Dados de elasticidade e otimização de precificação ML indisponíveis para este item.</Alert>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
