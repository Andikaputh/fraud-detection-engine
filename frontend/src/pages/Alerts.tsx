import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../lib/api";
import { formatDuration, formatIDR, formatNumber, relativeTime, shortId, titleCase } from "../lib/format";
import { useResource, useTicker } from "../lib/hooks";
import type { AlertStatus } from "../types";
import { AlertDrawer } from "../components/AlertDrawer";
import {
  AlertIcon,
  BellIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  SearchIcon,
} from "../components/icons";
import {
  EmptyState,
  ErrorState,
  RiskPill,
  SeverityBadge,
  Skeleton,
  StatusBadge,
} from "../components/ui";

const STATUS_TABS: { value: string; label: string }[] = [
  { value: "open,investigating", label: "Queue" },
  { value: "", label: "All" },
  { value: "open", label: "Open" },
  { value: "investigating", label: "Investigating" },
  { value: "resolved", label: "Resolved" },
  { value: "false_positive", label: "False positive" },
];

export function Alerts() {
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState("open,investigating");
  const [severity, setSeverity] = useState("");
  const [range, setRange] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("created_at");
  const [selected, setSelected] = useState<string | null>(params.get("focus"));
  const now = useTicker(15_000);

  useEffect(() => {
    setPage(1);
  }, [status, severity, range, search, sort]);

  useEffect(() => {
    if (selected) {
      params.set("focus", selected);
      setParams(params, { replace: true });
    } else if (params.get("focus")) {
      params.delete("focus");
      setParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const stats = useResource((signal) => api.alertStats(signal), "alert-stats", 15_000);
  const alerts = useResource(
    (signal) =>
      api.alerts(
        {
          page,
          page_size: 20,
          status: status || undefined,
          severity: severity || undefined,
          window: range || undefined,
          search: search || undefined,
          sort_by: sort,
        },
        signal,
      ),
    `alerts-${status}-${severity}-${range}-${search}-${page}-${sort}`,
    12_000,
  );

  const meta = alerts.data?.meta;
  const rows = alerts.data?.data || [];
  const tabs = useMemo(
    () =>
      STATUS_TABS.map((tab) => ({
        ...tab,
        count:
          tab.value === ""
            ? stats.data?.total
            : tab.value === "open,investigating"
              ? (stats.data?.open ?? 0) + (stats.data?.investigating ?? 0)
              : stats.data?.by_status?.[tab.value as AlertStatus] ?? 0,
      })),
    [stats.data],
  );

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <div className="eyebrow">
            <BellIcon size={13} /> Review operations
          </div>
          <h1>Alert queue</h1>
          <p>
            Every transaction above the review threshold becomes an alert with its full feature set, policy evidence
            and audit trail attached.
          </p>
        </div>
        <div className="page-header-actions">
          <div className="header-stat">
            <span>Unresolved critical</span>
            <strong>{stats.data?.open_critical ?? "N/A"}</strong>
          </div>
          <div className="header-stat">
            <span>Oldest open</span>
            <strong>{stats.data ? formatDuration(stats.data.oldest_open_minutes * 60) : "N/A"}</strong>
          </div>
          <div className="header-stat">
            <span>Closed 24h</span>
            <strong>{stats.data?.resolved_24h ?? "N/A"}</strong>
          </div>
        </div>
      </header>

      <div className="queue-summary">
        <div className="queue-card">
          <span className="queue-label">Awaiting triage</span>
          <strong>{formatNumber(stats.data?.open ?? 0)}</strong>
          <span className="queue-sub">open alerts</span>
        </div>
        <div className="queue-card">
          <span className="queue-label">In investigation</span>
          <strong>{formatNumber(stats.data?.investigating ?? 0)}</strong>
          <span className="queue-sub">assigned to analysts</span>
        </div>
        <div className="queue-card">
          <span className="queue-label">Critical severity</span>
          <strong>{formatNumber(stats.data?.by_severity?.critical ?? 0)}</strong>
          <span className="queue-sub">all time</span>
        </div>
        <div className="queue-card">
          <span className="queue-label">False positive rate</span>
          <strong>
            {stats.data
              ? `${((stats.data.false_positive / Math.max(stats.data.false_positive + stats.data.resolved, 1)) * 100).toFixed(1)}%`
              : "N/A"}
          </strong>
          <span className="queue-sub">of closed alerts</span>
        </div>
      </div>

      <section className="panel">
        <div className="queue-toolbar">
          <div className="status-tabs">
            {tabs.map((tab) => (
              <button
                key={tab.value}
                className={status === tab.value ? "active" : ""}
                onClick={() => setStatus(tab.value)}
              >
                {tab.label}
                <span>{typeof tab.count === "number" ? formatNumber(tab.count, true) : "N/A"}</span>
              </button>
            ))}
          </div>
          <div className="toolbar-right">
            <label className="table-search">
              <SearchIcon size={13} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search alert, customer, merchant"
                aria-label="Search alerts"
              />
            </label>
            <select value={severity} onChange={(event) => setSeverity(event.target.value)} aria-label="Severity filter">
              <option value="">All severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
            </select>
            <select value={range} onChange={(event) => setRange(event.target.value)} aria-label="Window filter">
              <option value="">All time</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
            </select>
            <select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort alerts">
              <option value="created_at">Newest first</option>
              <option value="risk_score">Highest risk</option>
            </select>
          </div>
        </div>

        {alerts.error ? <ErrorState message={alerts.error} /> : null}

        {alerts.loading && !alerts.data ? (
          <Skeleton rows={10} />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No alerts match these filters"
            message="Adjust the status, severity or time window to widen the search."
            icon={<AlertIcon size={18} />}
          />
        ) : (
          <div className="table-wrap">
            <table className="data-table alerts-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Alert</th>
                  <th>Merchant</th>
                  <th>Customer</th>
                  <th className="align-right">Amount</th>
                  <th>Risk</th>
                  <th>Status</th>
                  <th>Assignee</th>
                  <th className="align-right">Age</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((alert) => (
                  <tr key={alert.id} onClick={() => setSelected(alert.id)}>
                    <td>
                      <SeverityBadge severity={alert.severity} />
                    </td>
                    <td>
                      <div className="cell-primary mono">{shortId(alert.id, 9)}</div>
                      <div className="cell-sub mono">{shortId(alert.transaction_id, 10)}</div>
                    </td>
                    <td>
                      <div className="cell-primary">{alert.transaction?.merchant_name || "N/A"}</div>
                      <div className="cell-sub">
                        {alert.transaction ? `${titleCase(alert.transaction.merchant_category)} · ${alert.transaction.merchant_country}` : "N/A"}
                      </div>
                    </td>
                    <td className="mono">{alert.transaction?.customer_id || "N/A"}</td>
                    <td className="align-right mono amount-cell">
                      {alert.transaction ? formatIDR(alert.transaction.amount) : "N/A"}
                    </td>
                    <td>
                      <RiskPill score={alert.risk_score} />
                    </td>
                    <td>
                      <StatusBadge status={alert.status} />
                    </td>
                    <td className={alert.assignee ? "" : "muted-text"}>{alert.assignee || "Unassigned"}</td>
                    <td className="align-right muted-text">
                      <span className="age-cell">
                        <ClockIcon size={12} /> {relativeTime(alert.created_at, now)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {meta ? (
          <div className="pagination">
            <span>
              Showing {(meta.page - 1) * meta.page_size + 1}-{Math.min(meta.page * meta.page_size, meta.total)} of{" "}
              {formatNumber(meta.total)} alerts
            </span>
            <div>
              <button
                className="icon-button bordered"
                disabled={page <= 1}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                aria-label="Previous page"
              >
                <ChevronLeftIcon size={15} />
              </button>
              <span className="page-indicator">
                {meta.page} / {meta.pages}
              </span>
              <button
                className="icon-button bordered"
                disabled={page >= meta.pages}
                onClick={() => setPage((value) => Math.min(meta.pages, value + 1))}
                aria-label="Next page"
              >
                <ChevronRightIcon size={15} />
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <AlertDrawer
        alertId={selected}
        onClose={() => setSelected(null)}
        onUpdated={() => {
          alerts.refresh();
          stats.refresh();
        }}
      />
    </div>
  );
}
