import { useMemo, useState } from "react";

import { api } from "../lib/api";
import {
  formatDate,
  formatIDR,
  formatNumber,
  formatPercent,
  formatTime,
  titleCase,
} from "../lib/format";
import { useResource } from "../lib/hooks";
import type { WindowKey } from "../types";
import { AreaChart, CHART_COLORS, Donut, HBarList, Sparkline } from "../components/charts";
import { ChartIcon, ClockIcon, RefreshIcon } from "../components/icons";
import {
  ErrorState,
  KpiCard,
  Panel,
  Segmented,
  Skeleton,
} from "../components/ui";

const WINDOWS: { value: WindowKey; label: string }[] = [
  { value: "1h", label: "1H" },
  { value: "6h", label: "6H" },
  { value: "24h", label: "24H" },
  { value: "7d", label: "7D" },
  { value: "30d", label: "30D" },
];

const RISK_COLORS = [CHART_COLORS.green, "#d8c15a", CHART_COLORS.amber, CHART_COLORS.red];

function ScoreHistogram({ data }: { data: { range: string; count: number }[] }) {
  const max = Math.max(...data.map((bin) => bin.count), 1);
  return (
    <div className="histogram" role="img" aria-label="Risk score distribution">
      {data.map((bin, index) => {
        const tone =
          index >= 8 ? "critical" : index >= 5 ? "high" : index >= 3 ? "elevated" : "low";
        return (
          <div className="histogram-column" key={bin.range}>
            <div className="histogram-track">
              <span
                className={`histogram-bar ${tone}`}
                style={{ height: `${Math.max((bin.count / max) * 100, bin.count > 0 ? 2 : 0)}%` }}
                title={`${bin.range}: ${formatNumber(bin.count)} transactions`}
              />
            </div>
            <span className="histogram-value">{formatNumber(bin.count, true)}</span>
            <span className="histogram-label">{bin.range.split("-")[0]}</span>
          </div>
        );
      })}
    </div>
  );
}

export function Analytics() {
  const [range, setRange] = useState<WindowKey>("7d");
  const analytics = useResource((signal) => api.analytics(range, signal), `analytics-${range}`, 20_000);
  const data = analytics.data;

  const totals = useMemo(() => {
    if (!data) return { blocked: 0, review: 0, fraud: 0 };
    return data.series.reduce(
      (acc, point) => ({
        blocked: acc.blocked + point.blocked,
        review: acc.review + point.review,
        fraud: acc.fraud + point.fraud,
      }),
      { blocked: 0, review: 0, fraud: 0 },
    );
  }, [data]);

  const metrics = data?.label_metrics;
  const driftValues = (key: "avg_risk" | "avg_model_score" | "block_rate") =>
    (data?.model_drift || []).map((row) => Number(row[key]) || 0);

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <div className="eyebrow">
            <ChartIcon size={13} /> Decision intelligence
          </div>
          <h1>Analytics</h1>
          <p>
            Aggregated decision behaviour, policy evidence and labelled detection quality. Figures cover the selected
            window unless a panel states otherwise.
          </p>
        </div>
        <div className="page-header-actions">
          <Segmented value={range} options={WINDOWS} onChange={setRange} ariaLabel="Analytics window" />
          <button className="icon-button bordered" onClick={analytics.refresh} aria-label="Refresh analytics">
            <RefreshIcon size={15} />
          </button>
        </div>
      </header>

      {analytics.error ? <ErrorState message={analytics.error} /> : null}

      <div className="kpi-grid">
        {data ? (
          <>
            <KpiCard
              label="Detection precision"
              value={metrics ? formatPercent(metrics.precision) : "N/A"}
              sub={metrics ? `${formatNumber(metrics.tp)} true positives` : "No labelled rows in window"}
            />
            <KpiCard
              label="Detection recall"
              value={metrics ? formatPercent(metrics.recall) : "N/A"}
              sub={metrics ? `${formatNumber(metrics.fn)} fraud missed` : "No labelled rows in window"}
            />
            <KpiCard
              label="F1 score"
              value={metrics ? formatPercent(metrics.f1) : "N/A"}
              sub="Review + block treated as flagged"
            />
            <KpiCard
              label="False positive rate"
              value={metrics ? formatPercent(metrics.false_positive_rate) : "N/A"}
              sub={metrics ? `${formatNumber(metrics.fp)} legitimate rows flagged` : "No labelled rows in window"}
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

      <div className="analytics-grid">
        <Panel
          className="span-8"
          title="Decision volume"
          subtitle={
            data
              ? `${formatNumber(data.coverage.transactions)} authorisations · ${data.window.toUpperCase()} through ${formatTime(data.series_through)} UTC`
              : "Loading"
          }
        >
          {data ? (
            <AreaChart
              data={data.series}
              height={272}
              xMode={range === "7d" || range === "30d" ? "date" : "time"}
              series={[
                { key: "total", label: "Authorisations", color: CHART_COLORS.blue, area: true },
                { key: "review", label: "Review", color: CHART_COLORS.amber },
                { key: "blocked", label: "Blocked", color: CHART_COLORS.red },
                { key: "fraud", label: "Labeled fraud", color: CHART_COLORS.violet },
              ]}
            />
          ) : (
            <Skeleton rows={7} />
          )}
        </Panel>

        <Panel className="span-4" title="Risk bands" subtitle="Distribution across the window">
          {data ? (
            <div className="risk-panel">
              <Donut
                segments={data.risk_distribution.map((band, index) => ({
                  label: band.band,
                  value: band.count,
                  color: RISK_COLORS[index],
                }))}
                total={data.risk_distribution.reduce((sum, band) => sum + band.count, 0)}
                centerLabel="scored"
              />
              <div className="risk-legend">
                {data.risk_distribution.map((band, index) => (
                  <div key={band.band}>
                    <span className="legend-swatch" style={{ background: RISK_COLORS[index] }} />
                    <span className="risk-band-label">{band.band}</span>
                    <strong>{formatNumber(band.count, true)}</strong>
                    <em>
                      {formatPercent(
                        band.count / Math.max(data.risk_distribution.reduce((sum, item) => sum + item.count, 0), 1),
                        1,
                      )}
                    </em>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <Skeleton rows={5} />
          )}
        </Panel>

        <Panel
          className="span-7"
          title="Risk score distribution"
          subtitle="Ten-point bins across all scored authorisations"
          actions={<span className="panel-note">Policy + model blend</span>}
        >
          {data ? <ScoreHistogram data={data.risk_histogram} /> : <Skeleton rows={6} />}
        </Panel>

        <Panel className="span-5" title="Policy signals" subtitle="Share of authorisations that triggered each rule">
          {data ? (
            <HBarList
              items={data.top_reasons.map((reason) => ({
                label: reason.label,
                value: reason.count,
                meta: formatPercent(reason.share),
              }))}
              color={CHART_COLORS.amber}
            />
          ) : (
            <Skeleton rows={5} />
          )}
        </Panel>

        <Panel
          className="span-12"
          title="Merchant category exposure"
          subtitle="Volume and block rate by category"
          flush
        >
          {data ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th className="align-right">Authorisations</th>
                    <th className="align-right">Blocked</th>
                    <th className="align-right">Block rate</th>
                    <th className="align-right">Volume</th>
                    <th>Block rate profile</th>
                  </tr>
                </thead>
                <tbody>
                  {data.categories.map((category) => (
                    <tr key={category.category}>
                      <td>
                        <div className="cell-primary">{titleCase(category.category)}</div>
                      </td>
                      <td className="align-right mono">{formatNumber(category.total)}</td>
                      <td className="align-right mono">{formatNumber(category.blocked)}</td>
                      <td className="align-right mono">{formatPercent(category.block_rate)}</td>
                      <td className="align-right mono amount-cell">{formatIDR(category.volume)}</td>
                      <td>
                        <div className="inline-meter">
                          <span
                            style={{
                              width: `${Math.max(category.block_rate * 100, 1)}%`,
                              background:
                                category.block_rate >= 0.1 ? CHART_COLORS.red : CHART_COLORS.amber,
                            }}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Skeleton rows={6} />
          )}
        </Panel>

        <Panel
          className="span-7"
          title="Model drift"
          subtitle="Daily average scores over the trailing seven days"
          flush
        >
          {data ? (
            <div className="table-wrap">
              <table className="data-table compact">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th className="align-right">Volume</th>
                    <th className="align-right">Avg risk</th>
                    <th className="align-right">Avg model</th>
                    <th className="align-right">Block rate</th>
                    <th>Risk trend</th>
                  </tr>
                </thead>
                <tbody>
                  {data.model_drift.map((row) => (
                    <tr key={row.date}>
                      <td className="mono">{formatDate(row.date)}</td>
                      <td className="align-right mono">{formatNumber(row.transactions, true)}</td>
                      <td className="align-right mono">{row.avg_risk.toFixed(1)}</td>
                      <td className="align-right mono">{row.avg_model_score.toFixed(1)}</td>
                      <td className="align-right mono">{formatPercent(row.block_rate)}</td>
                      <td>
                        <span className="drift-cell">
                          <Sparkline values={driftValues("avg_risk").slice(0, data.model_drift.indexOf(row) + 1)} width={90} height={22} />
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Skeleton rows={6} />
          )}
          <div className="panel-foot inset">
            <span>
              Model score is the calibrated behavioural component; risk includes policy evidence.
            </span>
          </div>
        </Panel>

        <Panel className="span-5" title="Evaluation detail" subtitle="Confusion matrix for labelled rows">
          {metrics ? (
            <div className="eval-panel">
              <div className="confusion-grid">
                <div className="confusion-cell tp">
                  <span>True positive</span>
                  <strong>{formatNumber(metrics.tp)}</strong>
                </div>
                <div className="confusion-cell fp">
                  <span>False positive</span>
                  <strong>{formatNumber(metrics.fp)}</strong>
                </div>
                <div className="confusion-cell fn">
                  <span>False negative</span>
                  <strong>{formatNumber(metrics.fn)}</strong>
                </div>
                <div className="confusion-cell tn">
                  <span>True negative</span>
                  <strong>{formatNumber(metrics.tn)}</strong>
                </div>
              </div>
              <dl className="kv-list tight">
                <div>
                  <dt>Flagged</dt>
                  <dd>{formatNumber(metrics.flagged)}</dd>
                </div>
                <div>
                  <dt>Labelled coverage</dt>
                  <dd>
                    {formatPercent(metrics.labelled_rows / Math.max(data?.coverage.transactions || 1, 1))} of{" "}
                    {formatNumber(data?.coverage.transactions || 0)}
                  </dd>
                </div>
                <div>
                  <dt>Label source</dt>
                  <dd>Synthetic generator</dd>
                </div>
              </dl>
              <p className="panel-caption">{metrics.note}</p>
            </div>
          ) : (
            <Skeleton rows={5} />
          )}
        </Panel>
      </div>

      <div className="analytics-summary">
        <div>
          <span className="summary-label">Window totals</span>
          <strong>{formatNumber(data?.coverage.transactions ?? 0)}</strong>
          <small>{formatNumber(totals.review)} review · {formatNumber(totals.blocked)} blocked</small>
        </div>
        <div>
          <span className="summary-label">Labeled fraud</span>
          <strong>{formatNumber(totals.fraud)}</strong>
          <small>{formatNumber(data?.coverage.labelled ?? 0)} rows carry ground truth</small>
        </div>
        <div>
          <span className="summary-label">Events scored</span>
          <strong>{formatNumber(data?.system.processed ?? 0, true)}</strong>
          <small>p50 {data ? data.system.latency.p50.toFixed(1) : "-"} ms · {data?.system.ingest_mode ?? "-"}</small>
        </div>
        <div>
          <span className="summary-label">Snapshot</span>
          <strong className="summary-time">{data ? formatTime(data.generated_at) : "N/A"}</strong>
          <small>
            <ClockIcon size={11} /> refreshed every 20 seconds
          </small>
        </div>
      </div>
    </div>
  );
}
