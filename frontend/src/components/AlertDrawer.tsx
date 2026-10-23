import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { formatDateTime, formatIDR, formatTime, relativeTime, shortId, titleCase } from "../lib/format";
import { operatorName, useResource, useTicker } from "../lib/hooks";
import type { Alert } from "../types";
import { RiskGauge } from "./charts";
import { Drawer } from "./Drawer";
import { useToast } from "./Toast";
import { ErrorState, ReasonList, SeverityBadge, Skeleton, StatusBadge } from "./ui";

function ActionTimeline({ alert }: { alert: Alert }) {
  const events = alert.events || [];
  return (
    <ol className="timeline">
      {events.map((event) => (
        <li key={`${event.id}-${event.created_at}`}>
          <span className={`timeline-dot ${event.action.includes("resolved") ? "done" : ""}`} />
          <div>
            <p className="timeline-title">{titleCase(event.action.replace("alert.", ""))}</p>
            <p className="timeline-meta">
              {event.actor} · {formatDateTime(event.created_at)}
            </p>
            {typeof event.metadata?.note === "string" && event.metadata.note ? (
              <p className="timeline-note">{event.metadata.note}</p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function AlertDrawer({
  alertId,
  onClose,
  onUpdated,
}: {
  alertId: string | null;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const { data, error, loading, refresh } = useResource(
    (signal) => api.alert(alertId || "", signal),
    `alert-${alertId}`,
    0,
    Boolean(alertId),
  );
  const toast = useToast();
  const now = useTicker(15_000);
  const [status, setStatus] = useState("open");
  const [assignee, setAssignee] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!data) return;
    setStatus(data.status);
    setAssignee(data.assignee || operatorName());
    setNote(data.note || "");
  }, [data?.id, data?.updated_at, data]);

  const save = async (overrides?: { status?: string }) => {
    if (!alertId) return;
    setSaving(true);
    try {
      await api.updateAlert(alertId, {
        status: overrides?.status || status,
        assignee: assignee || null,
        note,
      });
      toast.push("Alert updated", { message: `${alertId} saved.`, tone: "success" });
      refresh();
      onUpdated();
    } catch (err) {
      toast.push("Could not update alert", {
        message: err instanceof Error ? err.message : "Unknown error",
        tone: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  const transaction = data?.transaction;
  const reasons = transaction?.reasons || [];

  return (
    <Drawer
      open={Boolean(alertId)}
      onClose={onClose}
      width={620}
      title={data ? shortId(data.id) : "Alert"}
      subtitle={
        data
          ? `${shortId(data.transaction_id)} · opened ${relativeTime(data.created_at, now)}`
          : "Loading investigation"
      }
      badge={data ? <SeverityBadge severity={data.severity} /> : null}
    >
      {loading && !data ? <Skeleton rows={9} /> : null}
      {error ? <ErrorState message={error} /> : null}
      {data && data.id === alertId && transaction ? (
        <>
          <div className="alert-summary">
            <div className="alert-summary-main">
              <div className="alert-amount">{formatIDR(transaction.amount, false)}</div>
              <p>
                {transaction.merchant_name} · <span>{titleCase(transaction.merchant_category)}</span>
              </p>
              <div className="alert-badges">
                <StatusBadge status={data.status} />
                <span className="chip chip-quiet">{transaction.customer_id}</span>
                <span className="chip chip-quiet">{transaction.merchant_country}</span>
                <span className="chip chip-quiet">{titleCase(transaction.channel)}</span>
              </div>
            </div>
            <RiskGauge score={data.risk_score} size={160} />
          </div>

          <div className="score-breakdown four">
            <div>
              <span>Risk score</span>
              <strong className="mono">{data.risk_score}</strong>
            </div>
            <div>
              <span>Policy evidence</span>
              <strong className="mono">{transaction.rule_score.toFixed(1)}</strong>
            </div>
            <div>
              <span>Model score</span>
              <strong className="mono">{transaction.model_score.toFixed(1)}</strong>
            </div>
            <div>
              <span>Decision</span>
              <strong className={`decision-text ${transaction.decision}`}>{transaction.decision}</strong>
            </div>
          </div>

          <section className="drawer-section">
            <h3>Why this was flagged</h3>
            <ReasonList reasons={reasons} />
          </section>

          <section className="drawer-section">
            <h3>Transaction context</h3>
            <dl className="detail-grid">
              <div>
                <dt>Transaction</dt>
                <dd className="mono">{transaction.id}</dd>
              </div>
              <div>
                <dt>External order</dt>
                <dd>{transaction.external_id || "N/A"}</dd>
              </div>
              <div>
                <dt>Card</dt>
                <dd className="mono">{transaction.card_id || "N/A"}</dd>
              </div>
              <div>
                <dt>Device</dt>
                <dd className="mono">{transaction.device_id || "N/A"}</dd>
              </div>
              <div>
                <dt>IP country</dt>
                <dd>{transaction.ip_country || "N/A"}</dd>
              </div>
              <div>
                <dt>Email domain</dt>
                <dd>{transaction.email_domain || "N/A"}</dd>
              </div>
              <div>
                <dt>Authorised at</dt>
                <dd>{formatDateTime(transaction.created_at)}</dd>
              </div>
              <div>
                <dt>Latency</dt>
                <dd className="mono">{transaction.latency_ms.toFixed(1)} ms</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>{transaction.model_version}</dd>
              </div>
              <div>
                <dt>Ground truth</dt>
                <dd>{transaction.label ? titleCase(transaction.label) : "unlabelled"}</dd>
              </div>
            </dl>
          </section>

          <section className="drawer-section">
            <div className="section-heading">
              <h3>Investigation</h3>
              <span className="muted-text">{formatTime(data.updated_at)}</span>
            </div>
            <div className="form-grid">
              <label className="field">
                <span>Status</span>
                <select value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option value="open">Open</option>
                  <option value="investigating">Investigating</option>
                  <option value="resolved">Resolved</option>
                  <option value="false_positive">False positive</option>
                </select>
              </label>
              <label className="field">
                <span>Assignee</span>
                <input value={assignee} onChange={(event) => setAssignee(event.target.value)} placeholder="analyst handle" />
              </label>
            </div>
            <label className="field">
              <span>Investigation note</span>
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={3}
                placeholder="What did you verify? Cardholder contact, step-up outcome, related alerts…"
              />
            </label>
            <div className="form-actions">
              <button className="btn btn-primary" onClick={() => save()} disabled={saving}>
                {saving ? "Saving…" : "Save changes"}
              </button>
              <button className="btn btn-secondary" onClick={() => save({ status: "investigating" })} disabled={saving}>
                Acknowledge
              </button>
              <button className="btn btn-ghost" onClick={() => save({ status: "resolved" })} disabled={saving}>
                Resolve
              </button>
              <button className="btn btn-danger-ghost" onClick={() => save({ status: "false_positive" })} disabled={saving}>
                False positive
              </button>
            </div>
            {data.resolved_at ? (
              <p className="resolved-note">
                Closed {formatDateTime(data.resolved_at)} as <strong>{data.status.replace("_", " ")}</strong>.
              </p>
            ) : null}
          </section>

          <section className="drawer-section">
            <h3>Activity</h3>
            <ActionTimeline alert={data} />
          </section>

          <div className="drawer-actions">
            <span className="muted-text">Operator: {operatorName()}</span>
          </div>
        </>
      ) : null}
    </Drawer>
  );
}
