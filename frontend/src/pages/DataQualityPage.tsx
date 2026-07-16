import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getDataQualityHistory, getDataQualityReport } from "../api/endpoints";
import Alert from "../components/Alert";
import MetricCard from "../components/MetricCard";

export default function DataQualityPage() {
  const { data: report, isError } = useQuery({ queryKey: ["dq-report"], queryFn: getDataQualityReport, retry: false });
  const { data: history } = useQuery({ queryKey: ["dq-history"], queryFn: () => getDataQualityHistory(30) });

  return (
    <div>
      <div className="page-header">
        <h2>📊 Observabilidade de Qualidade de Dados (Lote)</h2>
        <p>
          Relatório de conformidade gerado pelas checagens de Data Quality executadas no Airflow: distribuição,
          completude e anomalias de volume histórico.
        </p>
      </div>

      {isError && <Alert kind="warning">Relatório de qualidade indisponível ou pipeline ainda não executada.</Alert>}

      {report && (
        <>
          <div className="card">
            <div className="metric-grid mb-0">
              <MetricCard label="Status Geral" value={report.status === "Passed" ? "🟢 PASSED" : "🔴 FAILED"} />
              <MetricCard label="Score de Conformidade" value={`${report.compliance_score}%`} delta="Objetivo: 100%" />
              <MetricCard label="Última Execução" value={new Date(report.timestamp).toLocaleString("pt-BR")} />
            </div>
          </div>

          {history && history.length > 0 && (
            <div className="card">
              <p className="card-title">📈 Linha do Tempo de Qualidade de Dados</p>
              <div style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={[...history].sort((a, b) => a.timestamp.localeCompare(b.timestamp))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="timestamp" stroke="#94a3b8" fontSize={10} tickFormatter={(v) => new Date(v).toLocaleDateString("pt-BR")} />
                    <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 100]} />
                    <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                    <Line type="monotone" dataKey="compliance_score" stroke="#3b82f6" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <p className="card-title">📜 Detalhes dos Testes de Qualidade</p>
          {report.tests.map((test) => (
            <div className="card" key={test.test_id} style={{ borderLeft: `4px solid ${test.status === "Passed" ? "#10b981" : "#ef4444"}` }}>
              <div className="flex justify-between items-center">
                <h4 style={{ margin: 0 }}>
                  [{test.test_id}] {test.name}
                </h4>
                <span className={`badge ${test.status === "Passed" ? "pass" : "fail"}`}>
                  {test.status === "Passed" ? "🟢 PASS" : "🔴 FAIL"}
                </span>
              </div>
              <p className="text-muted">{test.description}</p>
              <div className="flex gap-12 text-muted" style={{ fontSize: 13 }}>
                <span>🔍 Métrica: {test.metric_value}</span>
                <span>📏 Limite: {test.threshold}</span>
              </div>
              {test.details.length > 0 && (
                <details className="mt-16">
                  <summary className="text-muted" style={{ cursor: "pointer" }}>
                    Auditar detalhes
                  </summary>
                  <ul>
                    {test.details.map((d, idx) => (
                      <li key={idx}>{d}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
