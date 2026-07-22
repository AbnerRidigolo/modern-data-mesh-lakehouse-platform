import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  getFeatureFreshness,
  getFeatureRegistry,
  getOnlineFeatures,
  materializeFeatures,
} from "../api/endpoints";
import Alert from "../components/Alert";
import MetricCard from "../components/MetricCard";
import type { OnlineFeatures } from "../api/types";

export default function FeatureStorePage() {
  const queryClient = useQueryClient();
  const { data: registry } = useQuery({ queryKey: ["fs-registry"], queryFn: getFeatureRegistry, retry: false });
  const { data: freshness } = useQuery({ queryKey: ["fs-freshness"], queryFn: getFeatureFreshness, retry: false });

  const views = useMemo(() => (registry ? Object.keys(registry.feature_views) : []), [registry]);
  const [selectedView, setSelectedView] = useState("");
  const [entityId, setEntityId] = useState("");
  const [online, setOnline] = useState<OnlineFeatures | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);

  const activeView = selectedView || views[0] || "";
  const viewDef = registry?.feature_views[activeView];

  const materialize = useMutation({
    mutationFn: materializeFeatures,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["fs-freshness"] }),
  });

  async function lookup() {
    if (!activeView || !entityId.trim()) return;
    setLookupError(null);
    setOnline(null);
    try {
      const res = await getOnlineFeatures(activeView, entityId.trim());
      setOnline(res);
    } catch (err: unknown) {
      setLookupError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Erro na consulta online.",
      );
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>🗄️ Feature Store</h2>
        <p>
          Camada de features governada: <strong>offline store</strong> (feature views dbt/DuckDB) para treino via{" "}
          <strong>point-in-time join</strong> anti-leakage, e <strong>online store</strong> (Redis) materializado pelo
          Airflow para serving em baixa latência. O registry é declarativo (YAML) e versionado no git.
        </p>
      </div>

      {/* Freshness / monitoramento */}
      <div className="card">
        <div className="flex justify-between items-center">
          <p className="card-title" style={{ margin: 0 }}>
            📡 Frescor das Feature Views
          </p>
          <button
            type="button"
            className="btn secondary"
            onClick={() => materialize.mutate()}
            disabled={materialize.isPending}
          >
            {materialize.isPending ? "Materializando..." : "⚡ Materializar Online Store"}
          </button>
        </div>

        {materialize.isSuccess && (
          <Alert kind="success">
            Materializado:{" "}
            {Object.entries(materialize.data.views)
              .map(([v, r]) => `${v} (${r.entities_written} entidades, ${r.backend})`)
              .join(" · ")}
          </Alert>
        )}

        {freshness && (
          <div className="metric-grid mt-16 mb-0">
            {freshness.map((f) => (
              <MetricCard
                key={f.feature_view}
                label={`${f.feature_view} — ${f.rows} linhas`}
                value={f.age_hours !== null ? `${f.age_hours.toFixed(1)}h` : "—"}
                delta={f.is_stale ? `⚠️ stale (TTL ${f.ttl_hours}h)` : `✅ fresh (TTL ${f.ttl_hours}h)`}
                deltaTone={f.is_stale ? "negative" : "positive"}
              />
            ))}
          </div>
        )}
      </div>

      {/* Serving online */}
      <div className="card">
        <p className="card-title">🔎 Serving Online (baixa latência)</p>
        <div className="flex gap-12" style={{ flexWrap: "wrap" }}>
          <select className="select" style={{ maxWidth: 260 }} value={activeView} onChange={(e) => setSelectedView(e.target.value)}>
            {views.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <input
            className="input"
            style={{ marginBottom: 0, maxWidth: 260 }}
            placeholder={viewDef?.entity === "customer" ? "customer_id (ex: 1117)" : "product_name"}
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && lookup()}
          />
          <button type="button" className="btn" onClick={lookup} disabled={!entityId.trim()}>
            Consultar
          </button>
        </div>

        {lookupError && <Alert kind="warning">{lookupError}</Alert>}

        {online?.features && (
          <div className="mt-16">
            <p className="text-muted">
              Origem: <span className="badge pass">{online.source}</span>
              {online.event_timestamp && ` · timestamp: ${online.event_timestamp}`}
            </p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(online.features).map(([k, v]) => (
                    <tr key={k}>
                      <td>{k}</td>
                      <td>{String(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Registry / catálogo governado */}
      {viewDef && (
        <div className="card">
          <p className="card-title">📖 Registry — {activeView}</p>
          <p className="text-muted">
            {viewDef.description}
            <br />
            Entidade: <code>{viewDef.entity}</code> · Fonte offline: <code>{viewDef.source_table}</code> · Timestamp:{" "}
            <code>{viewDef.timestamp_field}</code> · Owner: <strong>{viewDef.owner}</strong> · TTL online:{" "}
            {(viewDef.online_ttl_seconds / 3600).toFixed(0)}h
          </p>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Tipo</th>
                  <th>Descrição</th>
                </tr>
              </thead>
              <tbody>
                {viewDef.features.map((f) => (
                  <tr key={f.name}>
                    <td>
                      <code>{f.name}</code>
                    </td>
                    <td>{f.dtype}</td>
                    <td>{f.description}</td>
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
