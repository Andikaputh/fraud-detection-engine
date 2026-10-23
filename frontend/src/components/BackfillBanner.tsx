import { api } from "../lib/api";
import { formatNumber } from "../lib/format";
import { useResource } from "../lib/hooks";
import { DatabaseIcon } from "./icons";

export function BackfillBanner() {
  const { data } = useResource((signal) => api.backfill(signal), "backfill-status", 2_500);

  if (!data?.active && !data?.error) return null;

  const percent = data?.percent ?? 0;
  return (
    <div className={`backfill-banner ${data?.error ? "failed" : ""}`} role="status">
      <span className="backfill-icon">
        <DatabaseIcon size={15} />
      </span>
      <div className="backfill-copy">
        <strong>
          {data?.error ? "Historical backfill failed" : "Building the historical baseline"}
        </strong>
        <span>
          {data?.error
            ? data.error
            : data?.total
              ? `${formatNumber(data.progress)} of ${formatNumber(data.total)} authorisations scored · ${percent.toFixed(0)}%`
              : "Generating two days of labelled traffic through the live scoring pipeline…"}
        </span>
      </div>
      {!data?.error ? (
        <div className="backfill-track" aria-hidden="true">
          <span style={{ width: `${Math.max(percent, 2)}%` }} />
        </div>
      ) : null}
      <span className="backfill-elapsed">{data ? `${data.elapsed_seconds}s` : ""}</span>
    </div>
  );
}
