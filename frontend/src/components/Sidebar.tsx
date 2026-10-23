import type { ReactElement } from "react";
import { NavLink } from "react-router-dom";

import { api } from "../lib/api";
import { useResource } from "../lib/hooks";
import { formatDuration, formatNumber } from "../lib/format";
import { useLive } from "../lib/LiveContext";
import {
  BellIcon,
  ChartIcon,
  CpuIcon,
  GridIcon,
  RadioIcon,
  SettingsIcon,
  ShieldIcon,
} from "./icons";

const NAV: {
  label: string;
  items: {
    to: string;
    label: string;
    icon: (props: { size?: number }) => ReactElement;
    end?: boolean;
    badge?: boolean;
  }[];
}[] = [
  {
    label: "Monitor",
    items: [
      { to: "/", label: "Overview", icon: GridIcon, end: true },
      { to: "/alerts", label: "Alert queue", icon: BellIcon, badge: true },
    ],
  },
  {
    label: "Insight",
    items: [
      { to: "/analytics", label: "Analytics", icon: ChartIcon },
      { to: "/model", label: "Model", icon: CpuIcon },
    ],
  },
  {
    label: "Operations",
    items: [{ to: "/settings", label: "Settings", icon: SettingsIcon }],
  },
];

function LogoMark() {
  return (
    <svg viewBox="0 0 32 32" className="logo-mark" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#11151b" />
      <path d="M16 5.5l8.5 3v6.2c0 5.3-3.4 9.7-8.5 11.8-5.1-2.1-8.5-6.5-8.5-11.8V8.5l8.5-3z" stroke="#6d9eff" strokeWidth="1.4" fill="none" />
      <path d="M11.5 16.2l3 3 6-6.4" stroke="#3ddc97" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: system } = useResource(api.system, "sidebar-system", 20_000);
  const live = useLive();
  const queueCount = system ? system.alerts.open + system.alerts.investigating : 0;
  const p50 = system?.pipeline.latency.p50 ?? 0;
  const mode = system?.ingest.mode ?? "simulator";

  return (
    <>
      {open ? <div className="sidebar-scrim" onClick={onClose} role="presentation" /> : null}
      <aside className={`sidebar ${open ? "is-open" : ""}`}>
        <div className="sidebar-brand">
          <LogoMark />
          <div>
            <span className="brand-name">Sentinel</span>
            <span className="brand-sub">Fraud operations</span>
          </div>
          <button className="icon-button sidebar-close" onClick={onClose} aria-label="Close navigation">
            ×
          </button>
        </div>

        <button className="workspace">
          <span className="workspace-avatar">MP</span>
          <span className="workspace-text">
            <span className="workspace-name">Meridian Pay</span>
            <span className="workspace-env">Production · ID</span>
          </span>
          <span className="workspace-chevron">⌄</span>
        </button>

        <nav className="sidebar-nav">
          {NAV.map((group) => (
            <div className="nav-group" key={group.label}>
              <p className="nav-label">{group.label}</p>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
                  onClick={onClose}
                >
                  <item.icon size={17} />
                  <span>{item.label}</span>
                  {item.badge && queueCount > 0 ? <span className="nav-badge">{queueCount > 99 ? "99+" : queueCount}</span> : null}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-spacer" />

        <div className="system-card">
          <div className="system-card-head">
            <span className={`pulse-dot ${live.connection === "live" ? "ok" : "warn"}`} />
            <span>Ingestion {live.connection === "live" ? "live" : live.connection}</span>
            <RadioIcon size={14} />
          </div>
          <dl className="system-grid">
            <div>
              <dt>Mode</dt>
              <dd>{mode}</dd>
            </div>
            <div>
              <dt>p50</dt>
              <dd>{p50.toFixed(1)} ms</dd>
            </div>
            <div>
              <dt>Uptime</dt>
              <dd>{system ? formatDuration(system.pipeline.uptime_seconds) : "N/A"}</dd>
            </div>
            <div>
              <dt>Scored</dt>
              <dd>{system ? formatNumber(system.pipeline.processed, true) : "N/A"}</dd>
            </div>
          </dl>
          <div className="system-card-foot">
            <span>{system?.pipeline.model_version ?? "model loading"}</span>
            <span>v{system?.service.version ?? "1.0.0"}</span>
          </div>
        </div>

        <div className="sidebar-foot">
          <ShieldIcon size={14} />
          <span>PCI-aware demo environment</span>
        </div>
      </aside>
    </>
  );
}
