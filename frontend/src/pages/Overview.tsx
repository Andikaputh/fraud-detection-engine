import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api";
import { formatDateTime, formatIDR, formatNumber, formatPercent, formatTime, relativeTime, shortId, titleCase } from "../lib/format";
import { useResource, useTicker } from "../lib/hooks";
import { useLive } from "../lib/LiveContext";
import type { Alert, SeriesPoint, TransactionSummary, WindowKey } from "../types";
import { AlertDrawer } from "../components/AlertDrawer";
import { AreaChart, CHART_COLORS, Donut, HBarList, Sparkline } from "../components/charts";
import {
  AlertIcon,
  BellIcon,
  ClockIcon,
  PauseIcon,
  PlayIcon,
  RefreshIcon,
  SearchIcon,
} from "../components/icons";
import { TransactionDrawer } from "../components/TransactionDrawer";
import {
  DecisionBadge,
  EmptyState,
  ErrorState,
  KpiCard,
  Panel,
  RiskPill,
  Segmented,
  SeverityBadge,
  Skeleton,
  StatusBadge,
} from "../components/ui";

const WINDOWS: { value: WindowKey; label: string }[] = [
  { value: "1h", label: "1H" },
  { value: "6h", label: "6H" },
  { value: "24h", label: "24H" },
  { value: "7d", label: "7D" },
  { value: "30d", label: "30D" },
];

const RISK_COLORS = [CHART_COLORS.green, "#d8c15a", CHART_COLORS.amber, CHART_COLORS.red];

type FeedRow = TransactionSummary;

function mergeRows(live: TransactionSummary[], recent: TransactionSummary[] | undefined): FeedRow[] {
  const rows: FeedRow[] = [];
  const seen = new Set<string>();
  for (const row of [...live, ...(recent || [])]) {
    if (seen.has(row.id)) continue;
    seen.add(row.id);
    rows.push(row);
  }
  return rows;
}

export function Overview() {
  const [range, setRange] = useState<WindowKey>("24h");
  const [feedFilter, setFeedFilter] = useState<"all" | "flagged">("all");
  const [search, setSearch] = useState("");
  const [selectedTransaction, setSelectedTransaction] = useState<string | null>(null);
  const [selectedAlert, setSelectedAlert] = useState<string | null>(null);
  const live = useLive();
  const now = useTicker(15_000);

  const overview = useResource((signal) => api.overview(range, signal), `overview-${range}`, 12_000);
  const recent = useResource(
    (signal) => api.transactions({ page_size: 18, window: range }, signal),
    `recent-${range}`,
    15_000,
  );
  const alerts = useResource(
    (signal) => api.alerts({ page_size: 6, status: "open,investigating", sort_by: "created_at" }, signal),
    "active-alerts",
    10_000,
  );

  const rows = useMemo(() => mergeRows(live.transactions, recent.data?.data), [live.transactions, recent.data]);
  const filteredRows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rows
      .filter((row) => (feedFilter === "all" ? true : row.decision !== "allow"))
      .filter((row) =>
        needle
          ? `${row.id} ${row.customer_id} ${row.merchant_name} ${row.merchant_country}`.toLowerCase().includes(needle)
          : true,
      )
      .slice(0, 14);
  }, [rows, feedFilter, search]);

  const data = overview.data;
  const seriesForSpark = (key: keyof SeriesPoint) => (data?.series || []).map((point) => Number(point[key]) || 0);
  const activeAlerts = alerts.data?.data || [];
  const p50 = data?.system.latency.p50 ?? 0;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <div className="eyebrow">
            <span className="live-dot" />
            Real-time decisioning
          </div>
          <h1>Transaction intelligence</h1>
          <p>
            Authorisation risk across the Meridian Pay estate. Policy and behavioural scores are computed in the
            request path; every decision is persisted with its evidence and can be reviewed.
          </p>
        </div>
        <div className="page-header-actions">
          <Segmented value={range} options={WINDOWS} onChange={setRange} ariaLabel="Time window" />
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => live.setPaused(!live.paused)}
            title={live.paused ? "Resume live feed" : "Pause live feed"}
          >
            {live.paused ? <PlayIcon size={14} /> : <PauseIcon size={14} />}
            {live.paused ? "Resume" : "Pause"}
          </button>
          <button
            className="icon-button bordered"
            onClick={() => {
              overview.refresh();
              recent.refresh();
              alerts.refresh();
            }}
            aria-label="Refresh dashboard"
          >
            <RefreshIcon size={15} />
          </button>
        </div>
      </header>

      {overview.error ? <ErrorState message={overview.error} /> : null}

      <div className="kpi-grid">
        {data ? (
          <>
            <KpiCard
              label="Authorisations"
              value={formatNumber(data.kpis.transactions.value, true)}
              sub="vs previous period"
              delta={data.kpis.transactions.delta_pct}
              chart={<Sparkline values={seriesForSpark("total")} />}
            />
            <KpiCard
              label="Blocked"
              value={formatNumber(data.kpis.blocked.value, true)}
              sub={`${formatPercent(data.decisions.block_rate)} block rate`}
              delta={data.kpis.blocked.delta_pct}
              chart={<Sparkline values={seriesForSpark("blocked")} color={CHART_COLORS.red} />}
            />
            <KpiCard
              label="Exposure prevented"
              value={formatIDR(data.kpis.exposure_prevented.value)}
              sub="Blocked volume at decision time"
              delta={data.kpis.exposure_prevented.delta_pct}
              chart={<Sparkline values={seriesForSpark("blocked")} color={CHART_COLORS.amber} />}
            />
            <KpiCard
              label="Decision latency"
              value={`${p50.toFixed(1)} ms`}
              sub={`p50 · ${formatNumber(data.system.processed, true)} scored this process`}
              chart={<Sparkline values={seriesForSpark("review")} color={CHART_COLORS.violet} />}
            />
          </>
        ) : (
          Array.from({ length: 4 }).map((_, index) => (
            <div className="kpi" key={index}>
              <Skeleton rows={3} />
            </div>
          ))
        )}
      </div>

      <div className="overview-grid">
        <Panel
          className="span-8"
          title="Authorisation volume"
          subtitle={
            data
              ? `Window ${data.window.toUpperCase()} · complete buckets through ${formatTime(data.series_through)} UTC · updated ${relativeTime(data.generated_at, now)}`
              : "Loading"
          }
          actions={
            <span className="panel-note">
              {data ? `${formatNumber(data.kpis.transactions.value)} total` : "N/A"}
            </span>
          }
        >
          {data ? (
            <AreaChart
              data={data.series}
              xMode={range === "7d" || range === "30d" ? "date" : "time"}
              series={[
                { key: "total", label: "Authorisations", color: CHART_COLORS.blue, area: true },
                { key: "blocked", label: "Blocked", color: CHART_COLORS.red, area: true },
                { key: "review", label: "Review", color: CHART_COLORS.amber },
              ]}
            />
          ) : (
            <Skeleton rows={6} />
          )}
        </Panel>

        <Panel className="span-4" title="Risk distribution" subtitle="Score bands for the selected window">
          {data ? (
            <div className="risk-panel">
              <Donut
                segments={data.risk_distribution.map((band, index) => ({
                  label: band.band,
                  value: band.count,
                  color: RISK_COLORS[index],
                }))}
                total={data.kpis.transactions.value}
                centerLabel="scored"
              />
              <div className="risk-legend">
                {data.risk_distribution.map((band, index) => (
                  <div key={band.band}>
                    <span className="legend-swatch" style={{ background: RISK_COLORS[index] }} />
                    <span className="risk-band-label">{band.band}</span>
                    <strong>{formatNumber(band.count, true)}</strong>
                    <em>{formatPercent(band.share, 1)}</em>
                  </div>
                ))}
              </div>
              <div className="decision-strip" aria-label="Decision mix">
                <span
                  className="seg-allow"
                  style={{ flexGrow: data.decisions.allow }}
                  title={`${data.decisions.allow} allowed`}
                />
                <span
                  className="seg-review"
                  style={{ flexGrow: data.decisions.review }}
                  title={`${data.decisions.review} in review`}
                />
                <span
                  className="seg-block"
                  style={{ flexGrow: data.decisions.block }}
                  title={`${data.decisions.block} blocked`}
                />
              </div>
              <div className="decision-legend">
                <span><i className="dot allow" />{formatPercent(data.decisions.allow / Math.max(data.kpis.transactions.value, 1))} allow</span>
                <span><i className="dot review" />{formatPercent(data.decisions.review / Math.max(data.kpis.transactions.value, 1))} review</span>
                <span><i className="dot block" />{formatPercent(data.decisions.block_rate)} block</span>
              </div>
            </div>
          ) : (
            <Skeleton rows={5} />
          )}
        </Panel>

        <Panel
          className="span-8 live-panel"
          title="Live transaction stream"
          subtitle={`Latest authorisations · ${formatNumber(live.received, true)} new since connect · SSE`}
          actions={
            <div className="feed-actions">
              <div className="mini-tabs">
                <button className={feedFilter === "all" ? "active" : ""} onClick={() => setFeedFilter("all")}>
                  All
                </button>
                <button className={feedFilter === "flagged" ? "active" : ""} onClick={() => setFeedFilter("flagged")}>
                  Flagged
                </button>
              </div>
              <label className="table-search">
                <SearchIcon size={13} />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Filter stream"
                  aria-label="Filter live stream"
                />
              </label>
            </div>
          }
          flush
        >
          {filteredRows.length === 0 ? (
            <EmptyState
              title={live.paused ? "Stream paused" : "Waiting for authorisations"}
              message={
                live.paused
                  ? "Resume the stream to continue appending decisions."
                  : "New decisions will appear here as they are scored by the engine."
              }
              icon={<AlertIcon size={18} />}
              action={
                live.paused ? (
                  <button className="btn btn-secondary btn-sm" onClick={() => live.setPaused(false)}>
                    Resume stream
                  </button>
                ) : null
              }
            />
          ) : (
            <div className="table-wrap">
              <table className="data-table feed-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Customer</th>
                    <th>Merchant</th>
                    <th className="align-right">Amount</th>
                    <th>Risk</th>
                    <th>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((row, index) => (
                    <tr
                      key={row.id}
                      onClick={() => setSelectedTransaction(row.id)}
                      className={index === 0 && Date.now() - new Date(row.created_at).getTime() < 4000 ? "row-new" : ""}
                    >
                      <td className="mono time-cell">{formatTime(row.created_at)}</td>
                      <td>
                        <div className="cell-primary mono">{row.customer_id}</div>
                        <div className="cell-sub mono">{shortId(row.id, 8)}</div>
                      </td>
                      <td>
                        <div className="cell-primary">{row.merchant_name}</div>
                        <div className="cell-sub">
                          {titleCase(row.merchant_category)} · {row.merchant_country}
                        </div>
                      </td>
                      <td className="align-right mono amount-cell">{formatIDR(row.amount)}</td>
                      <td>
                        <RiskPill score={row.risk_score} />
                      </td>
                      <td>
                        <DecisionBadge decision={row.decision} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="panel-foot">
            <span>
              <span className={`pulse-dot ${live.connection === "live" ? "ok" : "warn"}`} />
              {live.paused ? "Paused" : live.connection === "live" ? "Streaming" : live.connection}
            </span>
            <Link to="/alerts" className="text-link">
              Open alert queue →
            </Link>
          </div>
        </Panel>

        <div className="span-4 side-stack">
          <Panel
            title="Active alerts"
            subtitle="Highest-risk open investigations"
            actions={
              <Link to="/alerts" className="text-link">
                View all
              </Link>
            }
            flush
          >
            {alerts.data ? (
              activeAlerts.length === 0 ? (
                <EmptyState
                  title="Queue is clear"
                  message="No open or investigating alerts right now."
                  icon={<BellIcon size={18} />}
                />
              ) : (
                <div className="alert-list">
                  {activeAlerts.map((alert: Alert) => (
                    <button className="alert-list-item" key={alert.id} onClick={() => setSelectedAlert(alert.id)}>
                      <span className={`severity-dot ${alert.severity}`} />
                      <span className="alert-list-main">
                        <span className="alert-list-title">{alert.transaction?.merchant_name || "Unknown merchant"}</span>
                        <span className="alert-list-sub">
                          {formatIDR(alert.transaction?.amount || 0)} · {relativeTime(alert.created_at, now)}
                        </span>
                      </span>
                      <span className="alert-list-side">
                        <RiskPill score={alert.risk_score} label={false} />
                        <StatusBadge status={alert.status} />
                      </span>
                    </button>
                  ))}
                </div>
              )
            ) : (
              <Skeleton rows={4} />
            )}
          </Panel>

          <Panel title="System health" subtitle="Ingestion and inference">
            {data ? (
              <dl className="kv-list">
                <div>
                  <dt>Decision p50</dt>
                  <dd>{data.system.latency.p50.toFixed(1)} ms</dd>
                </div>
                <div>
                  <dt>Decision p95</dt>
                  <dd>{data.system.latency.p95.toFixed(1)} ms</dd>
                </div>
                <div>
                  <dt>Write queue</dt>
                  <dd>{formatNumber(data.system.writer.queued)} rows</dd>
                </div>
                <div>
                  <dt>Dropped rows</dt>
                  <dd>{formatNumber(data.system.writer.dropped)}</dd>
                </div>
                <div>
                  <dt>Stream clients</dt>
                  <dd>{data.system.subscribers}</dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd className="mono">{data.system.model_version}</dd>
                </div>
              </dl>
            ) : (
              <Skeleton rows={4} />
            )}
          </Panel>
        </div>

        <Panel className="span-6" title="Detection signals" subtitle="Policy rules that fired most often">
          {data ? (
            <HBarList
              items={data.top_reasons.map((reason) => ({ label: reason.label, value: reason.count }))}
              color={CHART_COLORS.blue}
            />
          ) : (
            <Skeleton rows={4} />
          )}
        </Panel>

        <Panel className="span-6" title="Merchant exposure" subtitle="Highest blocked volume in the window" flush>
          {data ? (
            <div className="table-wrap">
              <table className="data-table compact">
                <thead>
                  <tr>
                    <th>Merchant</th>
                    <th className="align-right">Blocked</th>
                    <th className="align-right">Volume</th>
                    <th className="align-right">Avg risk</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_merchants.slice(0, 5).map((merchant) => (
                    <tr key={merchant.name}>
                      <td>
                        <div className="cell-primary">{merchant.name}</div>
                        <div className="cell-sub">{titleCase(merchant.category)}</div>
                      </td>
                      <td className="align-right mono">
                        {merchant.blocked}/{merchant.total}
                      </td>
                      <td className="align-right mono">{formatIDR(merchant.volume)}</td>
                      <td className="align-right">
                        <span className={`inline-risk ${merchant.avg_risk >= 50 ? "high" : ""}`}>
                          {merchant.avg_risk.toFixed(1)}
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
        </Panel>
      </div>

      <footer className="page-foot">
        <span>
          <ClockIcon size={13} /> Snapshot {data ? formatDateTime(data.generated_at) : "N/A"}
        </span>
        <span>{data?.label_metrics ? `Detection precision ${formatPercent(data.label_metrics.precision)} · recall ${formatPercent(data.label_metrics.recall)}` : "Labels unavailable for this window"}</span>
        <span>
          <SeverityBadge severity="critical" /> {formatNumber(activeAlerts.filter((alert) => alert.severity === "critical").length)} critical in queue
        </span>
      </footer>

      <TransactionDrawer transactionId={selectedTransaction} onClose={() => setSelectedTransaction(null)} />
      <AlertDrawer
        alertId={selectedAlert}
        onClose={() => setSelectedAlert(null)}
        onUpdated={() => {
          alerts.refresh();
          overview.refresh();
        }}
      />
    </div>
  );
}
