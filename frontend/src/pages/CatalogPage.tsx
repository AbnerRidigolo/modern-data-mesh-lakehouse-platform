import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getCatalogDomains, getLineage, getQuarantineFile, listQuarantineFiles } from "../api/endpoints";
import Alert from "../components/Alert";
import LineageGraph from "../components/LineageGraph";

function QuarantinePanel({ domain, label }: { domain: string; label: string }) {
  const { data: files } = useQuery({ queryKey: ["quarantine", domain], queryFn: () => listQuarantineFiles(domain) });
  const [selected, setSelected] = useState<string>("");

  const { data: fileContent } = useQuery({
    queryKey: ["quarantine-file", domain, selected],
    queryFn: () => getQuarantineFile(domain, selected),
    enabled: Boolean(selected),
  });

  return (
    <div className="card">
      <p className="card-title">Quarentena {label}</p>
      {!files || files.length === 0 ? (
        <Alert kind="success">✅ Nenhum registro em quarentena para o domínio {label}.</Alert>
      ) : (
        <>
          <Alert kind="error">⚠️ {files.length} violações de contrato detectadas!</Alert>
          <select className="select" value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">Selecione um arquivo...</option>
            {files.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          {fileContent && (
            <pre className="mt-16" style={{ whiteSpace: "pre-wrap", fontSize: 12, overflowX: "auto" }}>
              {typeof fileContent.content === "string" ? fileContent.content : JSON.stringify(fileContent.content, null, 2)}
            </pre>
          )}
        </>
      )}
    </div>
  );
}

export default function CatalogPage() {
  const { data: domains } = useQuery({ queryKey: ["catalog-domains"], queryFn: getCatalogDomains });
  const { data: lineage, isError: lineageError } = useQuery({ queryKey: ["lineage"], queryFn: getLineage, retry: false });

  return (
    <div>
      <div className="page-header">
        <h2>🕸️ Catálogo de Governança Data Mesh</h2>
        <p>
          Em uma arquitetura Data Mesh, os domínios definem e expõem seus dados de forma documentada. Veja abaixo os
          Data Products ativos e o monitoramento de Contratos de Dados.
        </p>
      </div>

      <div className="metric-grid" style={{ alignItems: "start" }}>
        {domains &&
          Object.entries(domains).map(([key, domain]) => (
            <div className="card" key={key}>
              <p className="card-title">{domain.name}</p>
              <p className="text-muted">
                <strong>Proprietário:</strong> {domain.owner}
                <br />
                <strong>Interface:</strong> {domain.interface}
                <br />
                <strong>Stack de Escrita:</strong> {domain.write_stack}
                {domain.partitioning && (
                  <>
                    <br />
                    <strong>Particionamento:</strong> {domain.partitioning}
                  </>
                )}
              </p>
              <p className="card-title mt-16">Data Contract (Pydantic)</p>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Campo</th>
                      <th>Tipo</th>
                      <th>Obrigatório</th>
                    </tr>
                  </thead>
                  <tbody>
                    {domain.contract_fields.map((field) => (
                      <tr key={field.name}>
                        <td>{field.name}</td>
                        <td>{field.type}</td>
                        <td>{field.required ? "Sim" : "Não"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
      </div>

      <div className="page-header mt-16">
        <h2>🚨 Observabilidade de Contratos &amp; Quarentena</h2>
        <p>Registros que violam o contrato de dados de um domínio são rejeitados e enviados para quarentena.</p>
      </div>
      <div className="metric-grid" style={{ alignItems: "start" }}>
        <QuarantinePanel domain="crm" label="CRM" />
        <QuarantinePanel domain="ecommerce" label="E-Commerce" />
      </div>

      <div className="page-header mt-16">
        <h2>📊 Linhagem de Dados Analíticos (dbt Lineage Graph)</h2>
        <p>Linhagem gerada a partir do compilador do dbt Core, do staging até os marts analíticos e features de ML.</p>
      </div>
      <div className="card">
        {lineageError && (
          <Alert kind="info">Execute a pipeline no Airflow para gerar a linhagem dbt (dbt docs generate).</Alert>
        )}
        {lineage && <LineageGraph lineage={lineage} />}
      </div>
    </div>
  );
}
