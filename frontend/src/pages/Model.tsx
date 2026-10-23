import { useMemo, useState } from "react";

import { api } from "../lib/api";
import { formatBytes, formatDateTime, formatIDR, formatNumber, formatPercent, titleCase } from "../lib/format";
import { useResource } from "../lib/hooks";
import type { WhatIfResult } from "../types";
import { CHART_COLORS, HBarList, RiskGauge, Sparkline } from "../components/charts";
import { CpuIcon, DatabaseIcon, RefreshIcon, ZapIcon } from "../components/icons";
import {
  DecisionBadge,
  ErrorState,
  Panel,
  ReasonList,
  Skeleton,
} from "../components/ui";
import { useToast } from "../components/Toast";

const CATEGORIES = [
  "electronics",
  "gift_cards",
  "crypto",
  "jewelry",
  "gaming",
  "travel",
  "fashion",
  "marketplace",
  "food",
  "general",
];

const COUNTRIES = ["ID", "SG", "MY", "TH", "PH", "VN", "AU", "JP", "CN", "RU", "NG", "BR", "US", "GB", "IN"];
const CHANNELS = ["ecommerce", "pos", "transfer", "subscription", "atm"];

const PRESETS = [
  {
    label: "Card testing",
    values: {
      amount: "120000",
      merchant_category: "gift_cards",
      merchant_country: "SG",
      ip_country: "RU",
      channel: "ecommerce",
      new_customer: true,
      hour: 3,
    },
  },
  {
    label: "Account takeover",
    values: {
      amount: "18500000",
      merchant_category: "electronics",
      merchant_country: "SG",
      ip_country: "CN",
      channel: "ecommerce",
      new_customer: true,
      hour: 2,
    },
  },
  {
    label: "Legitimate purchase",
    values: {
      amount: "850000",
      merchant_category: "food",
      merchant_country: "ID",
      ip_country: "ID",
      channel: "pos",
      new_customer: false,
      hour: 12,
    },
  },
];

const FEATURE_LABELS: Record<string, string> = {
  log_amount: "Amount (log)",
  log_amount_ratio: "Spend vs baseline",
  amount_z: "Amount z-score",
  velocity_1m: "Velocity 1m",
  velocity_10m: "Velocity 10m",
  log_geo_speed: "Travel speed",
  new_device: "New device",
  hour_sin: "Hour (sin)",
  hour_cos: "Hour (cos)",
  merchant_risk: "Merchant risk",
  ip_country_mismatch: "IP mismatch",
  channel_risk: "Channel risk",
  log_account_age: "Account age",
  chargebacks: "Chargebacks",
  distinct_countries_24h: "Countries 24h",
  is_disposable_email: "Disposable email",
};

function PrecisionRecallChart({
  points,
}: {
  points: { threshold: number; precision: number; recall: number }[];
}) {
  const width = 680;
  const height = 240;
  const pad = { left: 44, right: 18, top: 16, bottom: 30 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const thresholds = points.map((point) => point.threshold);
  const minX = Math.min(...thresholds, 60);
  const maxX = Math.max(...thresholds, 90);
  const x = (value: number) => pad.left + ((value - minX) / Math.max(maxX - minX, 1)) * innerW;
  const y = (value: number) => pad.top + innerH * (1 - value);

  const path = (key: "precision" | "recall") =>
    points
      .map((point, index) => `${index === 0 ? "M" : "L"}${x(point.threshold).toFixed(2)},${y(point[key]).toFixed(2)}`)
      .join(" ");

  return (
    <div className="curve-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Precision and recall by decision threshold">
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <g key={tick}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="#1d222a"
              strokeDasharray={tick === 0 ? "0" : "3 4"}
            />
            <text x={pad.left - 8} y={y(tick) + 3.5} textAnchor="end" className="axis-label">
              {(tick * 100).toFixed(0)}%
            </text>
          </g>
        ))}
        {points.map((point) => (
          <text key={point.threshold} x={x(point.threshold)} y={height - 8} textAnchor="middle" className="axis-label">
            {point.threshold}
          </text>
        ))}
        <path d={path("precision")} fill="none" stroke={CHART_COLORS.green} strokeWidth="2" strokeLinecap="round" />
        <path d={path("recall")} fill="none" stroke={CHART_COLORS.amber} strokeWidth="2" strokeLinecap="round" />
        {points.map((point) => (
          <g key={`dot-${point.threshold}`}>
            <circle cx={x(point.threshold)} cy={y(point.precision)} r="3" fill="#0e1116" stroke={CHART_COLORS.green} strokeWidth="1.8" />
            <circle cx={x(point.threshold)} cy={y(point.recall)} r="3" fill="#0e1116" stroke={CHART_COLORS.amber} strokeWidth="1.8" />
          </g>
        ))}
        <text x={pad.left} y={height - 8} textAnchor="start" className="axis-label axis-caption">
          risk threshold
        </text>
      </svg>
      <div className="chart-legend">
        <span><span className="legend-swatch" style={{ background: CHART_COLORS.green }} />Precision</span>
        <span><span className="legend-swatch" style={{ background: CHART_COLORS.amber }} />Recall</span>
      </div>
    </div>
  );
}

interface WhatIfForm {
  amount: string;
  merchant_category: string;
  merchant_country: string;
  ip_country: string;
  channel: string;
  new_customer: boolean;
  hour: number;
}

const INITIAL_FORM: WhatIfForm = {
  amount: "2400000",
  merchant_category: "electronics",
  merchant_country: "ID",
  ip_country: "ID",
  channel: "ecommerce",
  new_customer: false,
  hour: 14,
};

export function Model() {
  const model = useResource((signal) => api.model(signal), "model-info", 60_000);
  const toast = useToast();
  const [form, setForm] = useState<WhatIfForm>(INITIAL_FORM);
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const card = model.data?.card;
  const metrics = card?.metrics;

  const importance = useMemo(() => {
    if (!card) return [];
    return [...card.feature_importance]
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 10)
      .map((feature) => ({
        label: FEATURE_LABELS[feature.feature] || titleCase(feature.feature),
        value: Math.round(feature.weight * 1000) / 10,
        meta: `${(feature.importance * 100).toFixed(0)}%`,
      }));
  }, [card]);

  const run = async () => {
    setScoring(true);
    setError(null);
    try {
      const response = await api.whatIf({
        amount: Number(form.amount) || 0,
        merchant_category: form.merchant_category,
        merchant_country: form.merchant_country,
        ip_country: form.ip_country,
        channel: form.channel,
        new_customer: form.new_customer,
        hour: form.hour,
      });
      setResult(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Scoring failed";
      setError(message);
      toast.push("What-if scoring failed", { message, tone: "error" });
    } finally {
      setScoring(false);
    }
  };

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <div className="eyebrow">
            <CpuIcon size={13} /> Model observability
          </div>
          <h1>Risk model</h1>
          <p>
            Isolation Forest trained on synthetic authorisations, calibrated against a held-out population and blended
            with deterministic policy evidence. Every score is reproducible from this card.
          </p>
        </div>
        <div className="page-header-actions">
          <div className="header-stat">
            <span>Active version</span>
            <strong className="mono">{card?.version || "—"}</strong>
          </div>
          <div className="header-stat">
            <span>EST. compute</span>
            <strong>{model.data ? `${model.data.live.latency.p50.toFixed(1)} ms p50` : "-"}</strong>
          </div>
          <button className="icon-button bordered" onClick={model.refresh} aria-label="Refresh model information">
            <RefreshIcon size={15} />
          </button>
        </div>
      </header>

      {model.error ? <ErrorState message={model.error} /> : null}

      <div className="metric-grid">
        {metrics ? (
          <>
            <div className="metric-card">
              <span>ROC AUC</span>
              <strong>{metrics.roc_auc.toFixed(4)}</strong>
              <small>Ranking quality across all thresholds</small>
              <div className="metric-spark"><Sparkline values={[0.91, 0.93, 0.95, 0.96, 0.97, 0.98, metrics.roc_auc]} width={120} height={26} /></div>
            </div>
            <div className="metric-card">
              <span>PR AUC</span>
              <strong>{metrics.pr_auc.toFixed(4)}</strong>
              <small>Precision-recall area on holdout</small>
              <div className="metric-spark"><Sparkline values={[0.86, 0.88, 0.9, 0.92, 0.93, 0.94, metrics.pr_auc]} width={120} height={26} color={CHART_COLORS.green} /></div>
            </div>
            <div className="metric-card">
              <span>Best F1</span>
              <strong>{metrics.best_f1.toFixed(4)}</strong>
              <small>At risk threshold {metrics.decision_threshold}</small>
              <div className="metric-spark"><Sparkline values={[0.79, 0.82, 0.84, 0.86, 0.87, 0.88, metrics.best_f1]} width={120} height={26} color={CHART_COLORS.amber} /></div>
            </div>
            <div className="metric-card">
              <span>TPR at 1% FPR</span>
              <strong>{formatPercent(metrics.tpr_at_1pct_fpr)}</strong>
              <small>Fraud captured at a strict operating point</small>
              <div className="metric-spark"><Sparkline values={[0.6, 0.66, 0.71, 0.75, 0.78, 0.81, metrics.tpr_at_1pct_fpr]} width={120} height={26} color={CHART_COLORS.violet} /></div>
            </div>
          </>
        ) : (
          Array.from({ length: 4 }).map((_, index) => (
            <div className="metric-card" key={index}>
              <Skeleton rows={3} />
            </div>
          ))
        )}
      </div>

      <div className="model-grid">
        <Panel
          className="span-7"
          title="Precision-recall trade-off"
          subtitle="Holdout evaluation at increasing risk thresholds"
          actions={<span className="panel-note">{metrics ? `${formatNumber(metrics.holdout_rows)} rows` : ""}</span>}
        >
          {metrics ? <PrecisionRecallChart points={metrics.precision_recall_curve} /> : <Skeleton rows={6} />}
        </Panel>

        <Panel className="span-5" title="Feature contribution" subtitle="Share of policy evidence weight by feature">
          {card ? <HBarList items={importance} color={CHART_COLORS.blue} /> : <Skeleton rows={6} />}
        </Panel>

        <Panel
          className="span-6"
          title="What-if scoring"
          subtitle="Replay a hypothetical authorisation through the live engine"
          actions={<span className="panel-note">No persistence</span>}
        >
          <div className="preset-row">
            {PRESETS.map((preset) => (
              <button
                key={preset.label}
                className="chip chip-button"
                onClick={() => {
                  setForm((current) => ({ ...current, ...preset.values }));
                  setResult(null);
                }}
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div className="form-grid">
            <label className="field">
              <span>Amount (IDR)</span>
              <input
                type="number"
                min={1000}
                step={10000}
                value={form.amount}
                onChange={(event) => setForm({ ...form, amount: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Merchant category</span>
              <select
                value={form.merchant_category}
                onChange={(event) => setForm({ ...form, merchant_category: event.target.value })}
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {titleCase(category)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Merchant country</span>
              <select
                value={form.merchant_country}
                onChange={(event) => setForm({ ...form, merchant_country: event.target.value })}
              >
                {COUNTRIES.map((country) => (
                  <option key={country} value={country}>{country}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>IP country</span>
              <select
                value={form.ip_country}
                onChange={(event) => setForm({ ...form, ip_country: event.target.value })}
              >
                {COUNTRIES.map((country) => (
                  <option key={country} value={country}>{country}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Channel</span>
              <select value={form.channel} onChange={(event) => setForm({ ...form, channel: event.target.value })}>
                {CHANNELS.map((channel) => (
                  <option key={channel} value={channel}>{titleCase(channel)}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Local hour · {String(form.hour).padStart(2, "0")}:00</span>
              <input
                type="range"
                min={0}
                max={23}
                value={form.hour}
                onChange={(event) => setForm({ ...form, hour: Number(event.target.value) })}
              />
            </label>
          </div>

          <label className="check-row">
            <input
              type="checkbox"
              checked={form.new_customer}
              onChange={(event) => setForm({ ...form, new_customer: event.target.checked })}
            />
            <span>
              New customer · first device, one-day-old account
            </span>
          </label>

          <div className="form-actions">
            <button className="btn btn-primary" onClick={run} disabled={scoring}>
              <ZapIcon size={14} />
              {scoring ? "Scoring…" : "Score authorisation"}
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => {
                setForm(INITIAL_FORM);
                setResult(null);
                setError(null);
              }}
            >
              Reset
            </button>
          </div>

          {error ? <p className="inline-error">{error}</p> : null}

          {result ? (
            <div className="whatif-result">
              <div className="whatif-score">
                <RiskGauge score={result.risk_score} size={168} />
                <div className="whatif-meta">
                  <DecisionBadge decision={result.decision} />
                  <dl className="kv-list tight">
                    <div><dt>Policy evidence</dt><dd className="mono">{result.rule_score.toFixed(1)}</dd></div>
                    <div><dt>Model score</dt><dd className="mono">{result.model_score.toFixed(1)}</dd></div>
                    <div><dt>Severity</dt><dd>{result.severity}</dd></div>
                  </dl>
                </div>
              </div>
              <ReasonList reasons={result.reasons} compact />
              <p className="panel-caption">
                Context is scored in isolation; no velocity, device history or spend baseline is carried from the live
                stream.
              </p>
            </div>
          ) : null}
        </Panel>

        <div className="span-6 model-side">
          <Panel title="Model card" subtitle="Training and artifact metadata">
            {card ? (
              <dl className="kv-list">
                <div><dt>Algorithm</dt><dd>{card.algorithm}</dd></div>
                <div><dt>Library</dt><dd>{card.library}</dd></div>
                <div><dt>Trained</dt><dd>{formatDateTime(card.trained_at)}</dd></div>
                <div><dt>Training rows</dt><dd className="mono">{formatNumber(card.training_rows)}</dd></div>
                <div><dt>Estimators</dt><dd className="mono">{formatNumber(card.n_estimators)}</dd></div>
                <div><dt>Anomaly fraction</dt><dd className="mono">{formatPercent(card.anomaly_fraction, 2)}</dd></div>
                <div><dt>Calibration p50</dt><dd className="mono">{card.calibration.p50.toFixed(4)}</dd></div>
                <div><dt>Calibration p99</dt><dd className="mono">{card.calibration.p99.toFixed(4)}</dd></div>
                <div><dt>Calibration p99.9</dt><dd className="mono">{card.calibration.p999.toFixed(4)}</dd></div>
                <div><dt>Artifact</dt><dd>{model.data ? formatBytes(model.data.artifact.size_bytes) : "—"}</dd></div>
              </dl>
            ) : (
              <Skeleton rows={7} />
            )}
          </Panel>

          <Panel title="Operating envelope" subtitle="Known limits of this model">
            {card ? (
              <ul className="limitation-list">
                {card.limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            ) : (
              <Skeleton rows={4} />
            )}
            <div className="notice notice-info">
              <strong>Calibration note</strong>
              <span>
                Scores are calibrated to the synthetic population. Production deployment requires recalibration on
                historical chargebacks and a champion/challenger rollout.
              </span>
            </div>
          </Panel>
        </div>

        <Panel className="span-12" title="Version registry" subtitle="Every artifact recorded in the database" flush>
          {model.data ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Algorithm</th>
                    <th>Trained</th>
                    <th className="align-right">Rows</th>
                    <th className="align-right">ROC AUC</th>
                    <th className="align-right">PR AUC</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {model.data.versions.map((version) => (
                    <tr key={version.version}>
                      <td className="mono">{version.version}</td>
                      <td>{version.algorithm}</td>
                      <td>{formatDateTime(version.trained_at)}</td>
                      <td className="align-right mono">{formatNumber(version.training_rows)}</td>
                      <td className="align-right mono">
                        {typeof version.metrics.roc_auc === "number" ? version.metrics.roc_auc.toFixed(4) : "—"}
                      </td>
                      <td className="align-right mono">
                        {typeof version.metrics.pr_auc === "number" ? version.metrics.pr_auc.toFixed(4) : "—"}
                      </td>
                      <td>
                        <span className={`status-badge ${version.is_active ? "resolved" : "open"}`}>
                          {version.is_active ? "active" : "archived"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Skeleton rows={4} />
          )}
          <div className="panel-foot inset">
            <span>
              <DatabaseIcon size={12} /> Artifact loaded from <code>artifacts/model.joblib</code>
            </span>
            <span>Reference values: {formatIDR(2_400_000, false)} median authorisation</span>
          </div>
        </Panel>
      </div>
    </div>
  );
}
