export interface ApiEnvelope<T> {
  source: "cache" | "database" | "database_json" | "database_qdrant";
  query_time_seconds?: number;
  data: T;
}

export interface HealthStatus {
  status: string;
  api_version: string;
  database_connected: boolean;
  database_path: string;
  cache_type: string;
}

export interface MonthlyKpi {
  sales_month: string;
  net_revenue: number;
  completed_orders_count: number;
  average_ticket: number;
  [key: string]: unknown;
}

export interface DeltaTableInfo {
  key: string;
  label: string;
  exists: boolean;
}

export interface DeltaHistoryEntry {
  version: number;
  timestamp: string | null;
  operation: string;
  userName: string | null;
  operationParameters: Record<string, unknown>;
}

export interface DeltaTableData {
  version: number;
  total_rows: number;
  returned_rows: number;
  records: Record<string, unknown>[];
}

export interface ContractField {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

export interface DomainInfo {
  name: string;
  owner: string;
  interface: string;
  write_stack: string;
  partitioning: string | null;
  contract_fields: ContractField[];
}

export type CatalogDomains = Record<string, DomainInfo>;

export interface QuarantineFile {
  file_name: string;
  content: unknown;
  raw?: boolean;
}

export interface LineageNode {
  parents: string[];
  layer: "staging" | "dimension" | "fact" | "mart" | "other";
}

export interface LineageResponse {
  nodes: Record<string, LineageNode>;
}

export interface PricingDetails {
  base_price: number;
  optimal_price: number;
  competitor_price: number;
  expected_daily_demand: number;
  projected_daily_revenue: number;
  current_daily_revenue: number;
  revenue_lift_pct: number;
}

export interface PricingMetadata {
  model_metrics: { r2_score: number; mae: number };
  feature_columns: string[];
  product_one_hot_columns: string[];
  optimal_prices: Record<string, PricingDetails>;
  last_trained: string;
}

export interface DriftProductStatus {
  status: string;
  p_value: number;
  ks_stat: number;
  baseline_count?: number;
  current_count?: number;
  message?: string;
}

export interface DriftStatus {
  overall_drift_detected: boolean;
  checked_at: string;
  products: Record<string, DriftProductStatus>;
}

export interface SimulationResult {
  product_name: string;
  simulated_price: number;
  projected_demand: number;
  projected_revenue: number;
  lift_vs_baseline_pct: number;
}

export interface SearchResultItem {
  id: number;
  score: number;
  name: string;
  description: string;
  category: string;
  pricing_details: {
    base_price: number;
    optimal_price: number;
    revenue_lift_pct: number;
  } | null;
}

export interface SearchLogEntry {
  timestamp: string;
  query: string;
  latency_seconds: number;
  source: string;
  top_match: string;
  top_score: number;
}

export interface DataQualityTest {
  test_id: string;
  name: string;
  description: string;
  status: "Passed" | "Failed";
  metric_value: number;
  threshold: string;
  details: string[];
}

export interface DataQualityReport {
  timestamp: string;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  compliance_score: number;
  status: "Passed" | "Failed";
  tests: DataQualityTest[];
}

export interface DataQualityHistoryEntry {
  timestamp: string;
  compliance_score: number;
  passed_tests: number;
  failed_tests: number;
  total_tests: number;
  status: "Passed" | "Failed";
}
