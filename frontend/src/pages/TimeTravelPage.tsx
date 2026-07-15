import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getDeltaData, getDeltaHistory, getDeltaTables, restoreDeltaTable } from "../api/endpoints";
import Alert from "../components/Alert";

export default function TimeTravelPage() {
  const queryClient = useQueryClient();
  const { data: tables } = useQuery({ queryKey: ["delta-tables"], queryFn: getDeltaTables });
  const [selected, setSelected] = useState<string>("");
  const [version, setVersion] = useState<number | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [restoreMessage, setRestoreMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!selected && tables && tables.length > 0) {
      setSelected(tables[0].key);
    }
  }, [tables, selected]);

  const table = tables?.find((t) => t.key === selected);

  const { data: history, isError: historyError } = useQuery({
    queryKey: ["delta-history", selected],
    queryFn: () => getDeltaHistory(selected),
    enabled: Boolean(selected) && table?.exists === true,
  });

  const latestVersion = history && history.length > 0 ? Math.max(...history.map((h) => h.version)) : 0;

  useEffect(() => {
    if (history && history.length > 0) {
      setVersion(latestVersion);
    }
  }, [selected, latestVersion, history]);

  const { data: versionData } = useQuery({
    queryKey: ["delta-data", selected, version],
    queryFn: () => getDeltaData(selected, version ?? undefined),
    enabled: Boolean(selected) && version !== null,
  });

  async function handleRestore() {
    if (version === null) return;
    setRestoring(true);
    setRestoreMessage(null);
    try {
      const res = await restoreDeltaTable(selected, version);
      setRestoreMessage(res.message);
      queryClient.invalidateQueries({ queryKey: ["delta-history", selected] });
    } catch (e) {
      setRestoreMessage(e instanceof Error ? e.message : "Erro ao executar restore.");
    } finally {
      setRestoring(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>Delta Lake Time Travel Engine</h2>
        <p>
          O Delta Lake mantém um log transacional completo (<code>_delta_log/</code>) para cada tabela. Audite o
          histórico de versões, visualize dados no passado e realize rollback do estado físico da tabela.
        </p>
      </div>

      <div className="card">
        <p className="card-title">Selecione o Data Product</p>
        <select className="select" value={selected} onChange={(e) => setSelected(e.target.value)}>
          {tables?.map((t) => (
            <option key={t.key} value={t.key}>
              {t.label}
            </option>
          ))}
        </select>
      </div>

      {table && !table.exists && (
        <Alert kind="warning">A tabela Delta '{table.label}' ainda não foi criada. Execute a pipeline no Airflow.</Alert>
      )}

      {historyError && <Alert kind="error">Erro ao carregar o histórico da tabela.</Alert>}

      {history && history.length > 0 && (
        <>
          <div className="card">
            <p className="card-title">📜 Histórico de Commits (Audit Log)</p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Versão</th>
                    <th>Timestamp</th>
                    <th>Operação</th>
                    <th>Usuário</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.version}>
                      <td>{h.version}</td>
                      <td>{h.timestamp}</td>
                      <td>{h.operation}</td>
                      <td>{h.userName ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <p className="card-title">🕰️ Viagem no Tempo (Time Travel Query)</p>
            <input
              type="range"
              min={0}
              max={latestVersion}
              value={version ?? latestVersion}
              onChange={(e) => setVersion(Number(e.target.value))}
              style={{ width: "100%" }}
            />
            <p className="text-muted">
              Exibindo dados na <strong>Versão {version ?? latestVersion}</strong> (mais recente: {latestVersion})
            </p>

            {versionData && (
              <div className="table-scroll mt-16">
                <table className="data-table">
                  <thead>
                    <tr>
                      {versionData.records[0] &&
                        Object.keys(versionData.records[0]).map((col) => <th key={col}>{col}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {versionData.records.map((row, idx) => (
                      <tr key={idx}>
                        {Object.keys(row).map((col) => (
                          <td key={col}>{String(row[col])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-muted mt-16">
                  Exibindo {versionData.returned_rows} de {versionData.total_rows} registros.
                </p>
              </div>
            )}
          </div>

          <div className="card">
            <p className="card-title">🚨 Ação de Recuperação (Restore / Rollback)</p>
            <Alert kind="warning">
              Esta ação irá reverter a tabela física '{table?.label}' ao estado exato da Versão {version ?? latestVersion}.
            </Alert>
            {restoreMessage && <Alert kind="info">{restoreMessage}</Alert>}
            <button type="button" className="btn danger" onClick={handleRestore} disabled={restoring || version === latestVersion}>
              {restoring ? "Restaurando..." : `Executar Restore para Versão ${version ?? latestVersion}`}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
