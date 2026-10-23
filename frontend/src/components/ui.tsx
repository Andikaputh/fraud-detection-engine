import type { ReactNode } from "react";

import { ArrowDownRightIcon, ArrowUpRightIcon } from "./icons";
import { formatDelta } from "../lib/format";

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
  flush = false,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <section className={`panel ${className}`}>
      {title || actions ? (
        <header className="panel-head">
          <div>
            {title ? <h2 className="panel-title">{title}</h2> : null}
            {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="panel-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className={flush ? "panel-body flush" : "panel-body"}>{children}</div>
    </section>
  );
}

export function Delta({ value, invert = false }: { value: number | null; invert?: boolean }) {
  if (value === null || value === undefined) return <span className="delta flat">—</span>;
  const positive = value > 0;
  const good = invert ? !positive : positive;
  const Icon = positive ? ArrowUpRightIcon : ArrowDownRightIcon;
  return (
    <span className={`delta ${value === 0 ? "flat" : good ? "good" : "bad"}`}>
      {value !== 0 ? <Icon size={12} /> : null}
      {formatDelta(value)}
    </span>
  );
}

export function KpiCard({
  label,
  value,
  sub,
  delta,
  invertDelta = false,
  chart,
}: {
  label: string;
  value: string;
  sub?: string;
  delta?: number | null;
  invertDelta?: boolean;
  chart?: ReactNode;
}) {
  return (
    <div className="kpi">
      <div className="kpi-top">
        <span className="kpi-label">{label}</span>
        {delta !== undefined ? <Delta value={delta ?? null} invert={invertDelta} /> : null}
      </div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-bottom">
        <span className="kpi-sub">{sub}</span>
        {chart ? <div className="kpi-chart">{chart}</div> : null}
      </div>
    </div>
  );
}

const RISK_TONE = (score: number) => (score >= 80 ? "critical" : score >= 55 ? "high" : score >= 30 ? "elevated" : "low");

export function RiskPill({ score, label = true }: { score: number; label?: boolean }) {
  return (
    <span className={`risk-pill ${RISK_TONE(score)}`}>
      <span className="risk-bar">
        <span style={{ width: `${Math.max(4, score)}%` }} />
      </span>
      {label ? <span className="risk-number">{score}</span> : null}
    </span>
  );
}

export function DecisionBadge({ decision }: { decision: string }) {
  return <span className={`decision-badge ${decision}`}>{decision}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge ${status}`}>{status.replace(/_/g, " ")}</span>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`severity-badge ${severity}`}>{severity}</span>;
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  ariaLabel?: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          className={option.value === value ? "active" : ""}
          onClick={() => onChange(option.value)}
          aria-pressed={option.value === value}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
  icon,
}: {
  title: string;
  message: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty">
      {icon ? <div className="empty-icon">{icon}</div> : null}
      <p className="empty-title">{title}</p>
      <p className="empty-message">{message}</p>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="notice notice-error">
      <strong>Unable to load data</strong>
      <span>{message}</span>
    </div>
  );
}

export function Skeleton({ rows = 3, className = "" }: { rows?: number; className?: string }) {
  return (
    <div className={`skeleton-wrap ${className}`}>
      {Array.from({ length: rows }).map((_, index) => (
        <div className="skeleton" key={index} style={{ width: `${88 - index * 9}%` }} />
      ))}
    </div>
  );
}

export function ReasonList({ reasons, compact = false }: { reasons: { code: string; label: string; weight: number; detail: string }[]; compact?: boolean }) {
  if (reasons.length === 0) return <p className="muted-text">No policy rules fired. The score comes from the behavioural model only.</p>;
  const max = Math.max(...reasons.map((reason) => reason.weight), 1);
  return (
    <ul className={`reason-list ${compact ? "compact" : ""}`}>
      {reasons.map((reason) => (
        <li key={reason.code}>
          <div className="reason-head">
            <span>{reason.label}</span>
            <span className="reason-weight">+{reason.weight}</span>
          </div>
          {!compact ? <p className="reason-detail">{reason.detail}</p> : null}
          <div className="reason-track">
            <span style={{ width: `${Math.max((reason.weight / max) * 100, 3)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <label className="toggle-row">
      <button
        type="button"
        className={`toggle ${checked ? "on" : ""}`}
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
      >
        <span />
      </button>
      <span>{label}</span>
    </label>
  );
}
