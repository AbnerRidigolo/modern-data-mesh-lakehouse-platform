import { apiClient } from "./client";
import type {
  ApiEnvelope,
  CatalogDomains,
  DataQualityHistoryEntry,
  DataQualityReport,
  DeltaHistoryEntry,
  DeltaTableData,
  DeltaTableInfo,
  DriftStatus,
  HealthStatus,
  LineageResponse,
  MonthlyKpi,
  PricingMetadata,
  QuarantineFile,
  SearchLogEntry,
  SearchResultItem,
  SimulationResult,
} from "./types";

export async function login(username: string, password: string): Promise<string> {
  const form = new URLSearchParams();
  form.set("username", username);
  form.set("password", password);
  const resp = await apiClient.post("/api/v1/auth/token", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return resp.data.access_token as string;
}

export async function getHealth(): Promise<HealthStatus> {
  const resp = await apiClient.get("/");
  return resp.data;
}

export async function getKpis(): Promise<ApiEnvelope<MonthlyKpi[]>> {
  const resp = await apiClient.get("/api/v1/kpis");
  return resp.data;
}

export async function clearCache(): Promise<void> {
  await apiClient.post("/api/v1/cache/clear");
}

export async function getDeltaTables(): Promise<DeltaTableInfo[]> {
  const resp = await apiClient.get("/api/v1/delta/tables");
  return resp.data;
}

export async function getDeltaHistory(tableKey: string): Promise<DeltaHistoryEntry[]> {
  const resp = await apiClient.get(`/api/v1/delta/${tableKey}/history`);
  return resp.data;
}

export async function getDeltaData(tableKey: string, version?: number): Promise<DeltaTableData> {
  const resp = await apiClient.get(`/api/v1/delta/${tableKey}/data`, {
    params: version !== undefined ? { version } : {},
  });
  return resp.data;
}

export async function restoreDeltaTable(tableKey: string, version: number) {
  const resp = await apiClient.post(`/api/v1/delta/${tableKey}/restore`, { version });
  return resp.data as { message: string; version: number };
}

export async function getCatalogDomains(): Promise<CatalogDomains> {
  const resp = await apiClient.get("/api/v1/catalog/domains");
  return resp.data;
}

export async function listQuarantineFiles(domain: string): Promise<string[]> {
  const resp = await apiClient.get(`/api/v1/quarantine/${domain}`);
  return resp.data.files;
}

export async function getQuarantineFile(domain: string, fileName: string): Promise<QuarantineFile> {
  const resp = await apiClient.get(`/api/v1/quarantine/${domain}/${encodeURIComponent(fileName)}`);
  return resp.data;
}

export async function getLineage(): Promise<LineageResponse> {
  const resp = await apiClient.get("/api/v1/lineage");
  return resp.data;
}

export async function getPricingMetadata(): Promise<PricingMetadata> {
  const resp = await apiClient.get("/api/v1/ml/pricing-metadata");
  return resp.data;
}

export async function getDriftStatus(): Promise<DriftStatus> {
  const resp = await apiClient.get("/api/v1/ml/drift-status");
  return resp.data;
}

export async function getDriftReportHtml(): Promise<string> {
  const resp = await apiClient.get("/api/v1/ml/drift-report", { responseType: "text" });
  return resp.data;
}

export async function simulatePricing(productName: string, price: number, isWeekend: boolean): Promise<SimulationResult> {
  const resp = await apiClient.post("/api/v1/ml/simulate", {
    product_name: productName,
    price,
    is_weekend: isWeekend,
  });
  return resp.data;
}

export async function searchProducts(query: string): Promise<ApiEnvelope<SearchResultItem[]>> {
  const resp = await apiClient.get("/api/v1/products/search", { params: { query } });
  return resp.data;
}

export async function getSearchLogs(limit = 50): Promise<SearchLogEntry[]> {
  const resp = await apiClient.get("/api/v1/search/logs", { params: { limit } });
  return resp.data;
}

export async function getDataQualityReport(): Promise<DataQualityReport> {
  const resp = await apiClient.get("/api/v1/data-quality/report");
  return resp.data;
}

export async function getDataQualityHistory(limit = 30): Promise<DataQualityHistoryEntry[]> {
  const resp = await apiClient.get("/api/v1/data-quality/history", { params: { limit } });
  return resp.data;
}
