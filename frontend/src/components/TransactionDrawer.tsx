import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { formatDecimal, formatIDR, formatNumber, formatTime, relativeTime, shortId, titleCase } from "../lib/format";
import { useResource, useTicker } from "../lib/hooks";
import type { Transaction } from "../types";
import { RiskGauge } from "./charts";
import { Drawer } from "./Drawer";
import { ErrorState, ReasonList, RiskPill, Skeleton } from "./ui";

const FEATURE_META: { key: string; label: string; format: (value: number) => string }[] = [
  { key: "velocity_1m", label: "Velocity · 1 min", format: (value) => `${formatNumber(value)} auth` },
  { key: "velocity_10m", label: "Velocity · 10 min", format: (value) => `${formatNumber(value)} auth` },
  { key: "log_amount_ratio", label: "Spend vs baseline", format: (value) => `${formatDecimal(Math.expm1(value))}×` },
  { key: "amount_z", label: "Amount z-score", format: (value) => `${formatDecimal(value)}σ` },
  { key: "log_geo_speed", label: "Implied travel speed", format: (value) => `${formatNumber(Math.expm1(value))} km/h` },
  { key: "new_device", label: "New device", format: (value) => (value >= 0.5 ? "Yes" : "No") },
  { key: "log_account_age", label: "Account age", format: (value) => `${formatNumber(Math.expm1(value))} days` },
  { key: "chargebacks", label: "Prior chargebacks", format: (value) => formatNumber(value) },
  { key: "distinct_countries_24h", label: "Countries · 24h", format: (value) => formatNumber(value) },
  { key: "merchant_risk", label: "Merchant risk tier", format: (value) => formatDecimal(value) },
  {
    key: "ip_country_mismatch",
    label: "IP mismatch",
    format: (value) => (value >= 0.5 ? "Yes" : "No"),
  },
  {
    key: "is_disposable_email",
    label: "Disposable email",
    format: (value) => (value >= 0.5 ? "Yes" : "No"),
  },
];

function Rows({ items }: { items: { label: string; value: string }[] }) {
  return (
    <dl className="detail-grid">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function TransactionContent({ data, onClose }: { data: { transaction: Transaction; alert: { id: string } | null }; onClose: () => void }) {
  const navigate = useNavigate();
  const now = useTicker(15_000);
  const [copied, setCopied] = useState(false);
  const transaction = data.transaction;

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(transaction.id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };
  return (
    <>
      <div className="score-strip">
        <RiskGauge score={transaction.risk_score} size={170} />
        <div className="score-strip-meta">
          <div>
            <span className="meta-label">Decision</span>
            <p className={`decision-text ${transaction.decision}`}>{transaction.decision}</p>
          </div>
          <div>
            <span className="meta-label">Amount</span>
            <p className="amount-large">{formatIDR(transaction.amount)}</p>
          </div>
          <div>
            <span className="meta-label">Model score</span>
            <p className="mono">{transaction.model_score.toFixed(1)}</p>
          </div>
        </div>
      </div>

      <section className="drawer-section">
        <h3>Transaction</h3>
        <Rows
          items={[
            { label: "Transaction ID", value: transaction.id },
            { label: "External ID", value: transaction.external_id || "N/A" },
            { label: "Merchant", value: transaction.merchant_name },
            { label: "Category", value: titleCase(transaction.merchant_category) },
            { label: "Country", value: transaction.merchant_country },
            { label: "Channel", value: titleCase(transaction.channel) },
            { label: "Customer", value: transaction.customer_id },
            { label: "Card", value: transaction.card_id || "N/A" },
            { label: "Device", value: transaction.device_id || "N/A" },
            { label: "IP country", value: transaction.ip_country || "N/A" },
            { label: "Email domain", value: transaction.email_domain || "N/A" },
            {
              label: "Created",
              value: `${formatTime(transaction.created_at)} · ${relativeTime(transaction.created_at, now)}`,
            },
            { label: "Decision latency", value: `${transaction.latency_ms.toFixed(1)} ms` },
            { label: "Model version", value: transaction.model_version },
          ]}
        />
      </section>

      <section className="drawer-section">
        <h3>Risk factors</h3>
        <ReasonList reasons={transaction.reasons} />
      </section>

      <section className="drawer-section">
        <h3>Behavioural features</h3>
        <div className="feature-grid">
          {FEATURE_META.map((feature) => {
            const value = transaction.features[feature.key];
            if (value === undefined) return null;
            return (
              <div className="feature-cell" key={feature.key}>
                <span>{feature.label}</span>
                <strong>{feature.format(value)}</strong>
              </div>
            );
          })}
        </div>
      </section>

      <section className="drawer-section">
        <h3>Scoring</h3>
        <div className="score-breakdown">
          <div>
            <span>Risk score</span>
            <RiskPill score={transaction.risk_score} />
          </div>
          <div>
            <span>Policy evidence</span>
            <strong className="mono">{transaction.rule_score.toFixed(1)}</strong>
          </div>
          <div>
            <span>Behavioural model</span>
            <strong className="mono">{transaction.model_score.toFixed(1)}</strong>
          </div>
        </div>
        {transaction.label ? (
          <p className="label-note">
            Synthetic ground truth: <strong>{transaction.label}</strong>. Labels exist because the demo dataset is
            generated; a production deployment would attach chargeback outcomes.
          </p>
        ) : null}
      </section>

      <div className="drawer-actions">
        {data.alert ? (
          <button
            className="btn btn-primary"
            onClick={() => {
              onClose();
              navigate(`/alerts?focus=${data.alert?.id}`);
            }}
          >
            Open investigation
          </button>
        ) : null}
        <button className="btn btn-ghost" onClick={copyId}>
          {copied ? "Copied" : "Copy transaction ID"}
        </button>
      </div>
    </>
  );
}

export function TransactionDrawer({
  transactionId,
  onClose,
}: {
  transactionId: string | null;
  onClose: () => void;
}) {
  const { data, error, loading } = useResource(
    (signal) => api.transaction(transactionId || "", signal),
    `transaction-${transactionId}`,
    0,
    Boolean(transactionId),
  );

  return (
    <Drawer
      open={Boolean(transactionId)}
      onClose={onClose}
      title={transactionId ? shortId(transactionId) : "Transaction"}
      subtitle="Authorisation decision record"
      width={560}
    >
      {loading ? <Skeleton rows={8} /> : null}
      {error ? <ErrorState message={error} /> : null}
      {data && data.transaction.id === transactionId ? (
        <TransactionContent data={data} onClose={onClose} />
      ) : null}
    </Drawer>
  );
}
