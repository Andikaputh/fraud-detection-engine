export type WindowKey = "1h" | "6h" | "24h" | "7d" | "30d";
export type Decision = "allow" | "review" | "block";
export type Severity = "critical" | "high" | "medium";
export type AlertStatus = "open" | "investigating" | "resolved" | "false_positive";

export interface Reason {
  code: string;
  label: string;
  weight: number;
  detail: string;
}

export interface Transaction {
  id: string;
  external_id: string | null;
  customer_id: string;
  card_id: string | null;
  amount: number;
  currency: string;
  merchant_id: string;
  merchant_name: string;
  merchant_category: string;
  merchant_country: string;
  channel: string;
  device_id: string | null;
  ip_country: string | null;
  email_domain: string | null;
  risk_score: number;
  model_score: number;
  rule_score: number;
  decision: Decision;
  reasons: Reason[];
  features: Record<string, number>;
  model_version: string;
  latency_ms: number;
  label: "fraud" | "legit" | null;
  created_at: string;
  scored_at: string;
}

export interface TransactionSummary {
  id: string;
  customer_id: string;
  amount: number;
  currency: string;
  merchant_name: string;
  merchant_category: string;
  merchant_country: string;
  channel: string;
  risk_score: number;
  model_score: number;
  decision: Decision;
  reasons: Reason[];
  created_at: string;
  latency_ms: number;
  label: "fraud" | "legit" | null;
  alert_id?: string | null;
}

export interface AlertEvent {
  id: number;
  actor: string;
  action: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Alert {
  id: string;
  transaction_id: string;
  severity: Severity;
  risk_score: number;
  status: AlertStatus;
  assignee: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  transaction: Transaction | null;
  events?: AlertEvent[];
  policy?: { review_threshold: number; block_threshold: number };
}

export interface PageMeta {
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface TransactionPage {
  data: Transaction[];
  meta: PageMeta;
}

export interface AlertPage {
  data: Alert[];
  meta: PageMeta;
}

export interface SeriesPoint {
  t: string;
  total: number;
  blocked: number;
  review: number;
  fraud: number;
}

export interface LabelMetrics {
  flagged: number;
  tp: number;
  fp: number;
  fn: number;
  tn: number;
  precision: number;
  recall: number;
  f1: number;
  false_positive_rate: number;
  labelled_rows: number;
  note: string;
}

export interface SystemStatus {
  service: {
    name: string;
    version: string;
    environment: string;
    demo_mode: boolean;
  };
  pipeline: {
    uptime_seconds: number;
    processed: number;
    counters: { total: number; allow: number; review: number; block: number; fraud_label: number };
    latency: { p50: number; p95: number; p99: number; avg: number };
    last_event_at: string | null;
    ingest_mode: string;
    subscribers: number;
    writer: {
      queued: number;
      written: number;
      alerts_written: number;
      dropped: number;
      failed_batches: number;
      last_flush_ms: number;
    };
    model_version: string;
  };
  ingest: {
    mode: string;
    running?: boolean;
    emitted?: number;
    tps?: number;
    connected?: boolean;
    consumed?: number;
    topic?: string;
    last_error?: string | null;
  };
  alerts: AlertStats;
  delivery: {
    configured: boolean;
    telegram_configured: boolean;
    webhook_configured: boolean;
    sent: number;
    failed: number;
    skipped: number;
    queued: number;
    last_error: string | null;
  };
  storage: { engine: string; size_bytes: number | null; retention_days: number };
  config: EngineSettings;
  backfill: BackfillStatus;
  server_time: string;
}

export interface BackfillStatus {
  active: boolean;
  progress: number;
  total: number;
  percent: number | null;
  elapsed_seconds: number;
  error: string | null;
  summary: { transactions: number; alerts: number; days: number } | null;
}

export interface AlertStats {
  total: number;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  open: number;
  investigating: number;
  resolved: number;
  false_positive: number;
  open_critical: number;
  resolved_24h: number;
  oldest_open_minutes: number;
}

export interface KpiValue {
  value: number;
  previous: number;
  delta_pct: number | null;
}

export interface Overview {
  window: WindowKey;
  generated_at: string;
  series_through: string;
  kpis: {
    transactions: KpiValue;
    blocked: KpiValue;
    review: KpiValue;
    exposure_prevented: KpiValue;
    avg_risk: KpiValue;
    approval_rate: KpiValue;
  };
  series: SeriesPoint[];
  risk_distribution: { band: string; count: number; share: number }[];
  decisions: { allow: number; review: number; block: number; block_rate: number };
  top_reasons: { code: string; label: string; count: number }[];
  top_merchants: {
    name: string;
    category: string;
    total: number;
    blocked: number;
    avg_risk: number;
    volume: number;
  }[];
  channels: { channel: string; total: number; blocked: number; avg_risk: number; approval_rate: number }[];
  label_metrics: LabelMetrics | null;
  system: SystemStatus["pipeline"];
}

export interface Analytics {
  window: WindowKey;
  generated_at: string;
  series_through: string;
  series: SeriesPoint[];
  risk_histogram: { range: string; count: number }[];
  risk_distribution: { band: string; count: number }[];
  top_reasons: { code: string; label: string; count: number; share: number }[];
  categories: { category: string; total: number; blocked: number; volume: number; block_rate: number }[];
  model_drift: {
    date: string;
    transactions: number;
    avg_risk: number;
    avg_model_score: number;
    block_rate: number;
  }[];
  label_metrics: LabelMetrics | null;
  coverage: { transactions: number; labelled: number; window: string };
  system: SystemStatus["pipeline"];
}

export interface ModelCard {
  version: string;
  algorithm: string;
  library: string;
  trained_at: string;
  training_rows: number;
  anomaly_fraction: number;
  n_estimators: number;
  feature_names: string[];
  calibration: { p50: number; p99: number; p999: number };
  metrics: {
    roc_auc: number;
    pr_auc: number;
    precision_at_best_f1: number;
    recall_at_best_f1: number;
    best_f1: number;
    decision_threshold: number;
    tpr_at_1pct_fpr: number;
    holdout_rows: number;
    precision_recall_curve: { threshold: number; precision: number; recall: number }[];
    evaluation: string;
  };
  feature_importance: { feature: string; importance: number; weight: number }[];
  score_distribution: { p50: number; p90: number; p99: number };
  limitations: string[];
}

export interface ModelInfo {
  card: ModelCard;
  artifact: { path: string; size_bytes: number; loaded_at: string };
  versions: {
    version: string;
    algorithm: string;
    trained_at: string;
    training_rows: number;
    is_active: boolean;
    metrics: Record<string, unknown>;
  }[];
  live: SystemStatus["pipeline"];
}

export interface EngineSettings {
  review_threshold: number;
  block_threshold: number;
  amount_sensitivity: number;
  velocity_limit_1m: number;
  velocity_limit_10m: number;
  auto_block: boolean;
  telegram_enabled: boolean;
  simulator_tps: number;
  telegram_configured: boolean;
  webhook_configured: boolean;
  ingest_mode: string;
}

export interface WhatIfResult {
  risk_score: number;
  decision: Decision;
  model_score: number;
  rule_score: number;
  severity: Severity;
  reasons: Reason[];
  features: Record<string, number>;
  context: Record<string, number | string | boolean>;
}
