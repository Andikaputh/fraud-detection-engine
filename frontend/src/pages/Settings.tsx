import { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import { formatBytes, formatNumber, formatPercent, formatDuration } from "../lib/format";
import { useResource } from "../lib/hooks";
import type { EngineSettings } from "../types";
import {
  DatabaseIcon,
  RefreshIcon,
  SettingsIcon,
  ShieldIcon,
  ZapIcon,
} from "../components/icons";
import { ErrorState, Panel, Skeleton, Toggle } from "../components/ui";
import { useToast } from "../components/Toast";

type Draft = Partial<EngineSettings>;

const AMOUNT_OPTIONS = [
  { value: 5_000_000, label: "Rp 5M" },
  { value: 10_000_000, label: "Rp 10M" },
  { value: 20_000_000, label: "Rp 20M" },
  { value: 50_000_000, label: "Rp 50M" },
];

export function Settings() {
  const settings = useResource((signal) => api.settings(signal), "engine-settings", 20_000);
  const system = useResource((signal) => api.system(signal), "settings-system", 15_000);
  const toast = useToast();

  const [draft, setDraft] = useState<Draft>({});
  const [dirty, setDirty] = useState(false);
  const [initialised, setInitialised] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyPattern, setBusyPattern] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  const [operator, setOperator] = useState(() => localStorage.getItem("sentinel.operator") || "");
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("sentinel.apiKey") || "");

  useEffect(() => {
    if (settings.data && !initialised) {
      setDraft(settings.data);
      setInitialised(true);
    }
  }, [settings.data, initialised]);

  const review = draft.review_threshold ?? settings.data?.review_threshold ?? 60;
  const block = draft.block_threshold ?? settings.data?.block_threshold ?? 85;
  const invalid = review >= block || review < 1 || block > 100;
  const autoBlock = draft.auto_block ?? settings.data?.auto_block ?? true;
  const telegramEnabled = draft.telegram_enabled ?? settings.data?.telegram_enabled ?? false;
  const tps = draft.simulator_tps ?? settings.data?.simulator_tps ?? 0.2;
  const sensitivity = draft.amount_sensitivity ?? settings.data?.amount_sensitivity ?? 10_000_000;
  const velocity1m = draft.velocity_limit_1m ?? settings.data?.velocity_limit_1m ?? 5;
  const velocity10m = draft.velocity_limit_10m ?? settings.data?.velocity_limit_10m ?? 12;

  const update = <K extends keyof EngineSettings>(key: K, value: EngineSettings[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setDirty(true);
  };

  const save = async () => {
    if (invalid) return;
    setSaving(true);
    try {
      const updated = await api.updateSettings({
        review_threshold: review,
        block_threshold: block,
        auto_block: autoBlock,
        telegram_enabled: telegramEnabled,
        simulator_tps: tps,
        amount_sensitivity: sensitivity,
        velocity_limit_1m: velocity1m,
        velocity_limit_10m: velocity10m,
      });
      setDraft(updated);
      setDirty(false);
      toast.push("Policy updated", {
        message: `Review ${updated.review_threshold} · block ${updated.block_threshold} · ${updated.simulator_tps.toFixed(1)} tps`,
        tone: "success",
      });
      settings.refresh();
      system.refresh();
    } catch (error) {
      toast.push("Could not save settings", {
        message: error instanceof Error ? error.message : "Unknown error",
        tone: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  const burst = async (pattern: string, count: number, label: string) => {
    setBusyPattern(pattern);
    try {
      const result = await api.burst(pattern, count);
      toast.push(`${label} injected`, {
        message: `${result.accepted} authorisations scored in ${result.elapsed_ms} ms.`,
        tone: "success",
      });
      system.refresh();
    } catch (error) {
      toast.push("Simulation failed", {
        message: error instanceof Error ? error.message : "Unknown error",
        tone: "error",
      });
    } finally {
      setBusyPattern(null);
    }
  };

  const resetDemo = async () => {
    if (!window.confirm("Reset the demo environment? This deletes all transactions, alerts and audit history, then rebuilds seven days of history through the live scoring pipeline.")) {
      return;
    }
    setResetting(true);
    try {
      await api.resetDemo();
      toast.push("Rebuild started", {
        message: "The dashboard will update as the two-day baseline is scored.",
        tone: "success",
      });
      settings.refresh();
      system.refresh();
    } catch (error) {
      toast.push("Reset failed", {
        message: error instanceof Error ? error.message : "Unknown error",
        tone: "error",
      });
    } finally {
      setResetting(false);
    }
  };

  const saveIdentity = () => {
    if (operator.trim()) localStorage.setItem("sentinel.operator", operator.trim());
    else localStorage.removeItem("sentinel.operator");
    if (apiKey.trim()) localStorage.setItem("sentinel.apiKey", apiKey.trim());
    else localStorage.removeItem("sentinel.apiKey");
    toast.push("Operator identity saved", {
      message: "It will be attached to subsequent write requests from this browser.",
      tone: "success",
    });
  };

  const delivery = system.data?.delivery;
  const storage = system.data?.storage;
  const mode = settings.data?.ingest_mode ?? "—";

  const thresholdMarkers = useMemo(
    () => [
      { value: review, label: "Review", tone: "review" },
      { value: block, label: "Block", tone: "block" },
    ],
    [review, block],
  );

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <div className="eyebrow">
            <SettingsIcon size={13} /> Environment control
          </div>
          <h1>Settings</h1>
          <p>
            Decision thresholds, simulator throughput and integration status for this environment. Changes are applied
            to the running pipeline and recorded in the audit log.
          </p>
        </div>
        <div className="page-header-actions">
          <span className={`state-pill ${dirty ? "dirty" : ""}`}>
            {dirty ? "Unsaved changes" : "In sync"}
          </span>
          <button className="icon-button bordered" onClick={() => { settings.refresh(); system.refresh(); }} aria-label="Refresh settings">
            <RefreshIcon size={15} />
          </button>
          <button className="btn btn-primary" onClick={save} disabled={saving || invalid || !dirty}>
            {saving ? "Applying…" : "Apply changes"}
          </button>
        </div>
      </header>

      {settings.error ? <ErrorState message={settings.error} /> : null}

      <div className="settings-grid">
        <Panel
          className="span-7"
          title="Decision policy"
          subtitle="Risk score bands applied to every authorisation"
          actions={<span className="panel-note">{mode}</span>}
        >
          {settings.data ? (
            <>
              <div className="threshold-visual" aria-hidden="true">
                <div className="threshold-track">
                  <span className="band-allow" style={{ width: `${review}%` }} />
                  <span className="band-review" style={{ width: `${Math.max(block - review, 0)}%` }} />
                  <span className="band-block" style={{ width: `${Math.max(100 - block, 0)}%` }} />
                  {thresholdMarkers.map((marker) => (
                    <span
                      key={marker.label}
                      className={`threshold-marker ${marker.tone}`}
                      style={{ left: `${marker.value}%` }}
                    >
                      <em>{marker.label}</em>
                    </span>
                  ))}
                </div>
                <div className="threshold-legend">
                  <span><i className="dot allow" />Allow 0–{review}</span>
                  <span><i className="dot review" />Review {review}–{block}</span>
                  <span><i className="dot block" />Block {block}–100</span>
                </div>
              </div>

              <div className="form-grid">
                <label className="field">
                  <span>Review threshold</span>
                  <div className="input-suffix">
                    <input
                      type="number"
                      min={1}
                      max={99}
                      value={review}
                      onChange={(event) => update("review_threshold", Number(event.target.value))}
                    />
                    <span>risk</span>
                  </div>
                </label>
                <label className="field">
                  <span>Block threshold</span>
                  <div className="input-suffix">
                    <input
                      type="number"
                      min={2}
                      max={100}
                      value={block}
                      onChange={(event) => update("block_threshold", Number(event.target.value))}
                    />
                    <span>risk</span>
                  </div>
                </label>
                <label className="field">
                  <span>Velocity limit · 1 minute</span>
                  <input
                    type="number"
                    min={1}
                    max={60}
                    value={velocity1m}
                    onChange={(event) => update("velocity_limit_1m", Number(event.target.value))}
                  />
                </label>
                <label className="field">
                  <span>Velocity limit · 10 minutes</span>
                  <input
                    type="number"
                    min={2}
                    max={240}
                    value={velocity10m}
                    onChange={(event) => update("velocity_limit_10m", Number(event.target.value))}
                  />
                </label>
                <label className="field span-full">
                  <span>Amount sensitivity</span>
                  <select
                    value={sensitivity}
                    onChange={(event) => update("amount_sensitivity", Number(event.target.value))}
                  >
                    {AMOUNT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label} — high-value screening begins here
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="setting-toggles">
                <Toggle
                  checked={autoBlock}
                  onChange={(value) => update("auto_block", value)}
                  label="Automatically block authorisations above the block threshold"
                />
                <p className="field-hint">
                  When disabled, transactions above the block threshold remain in review instead of being declined.
                </p>
              </div>

              {invalid ? (
                <p className="inline-error">Review threshold must be lower than the block threshold.</p>
              ) : null}
            </>
          ) : (
            <Skeleton rows={8} />
          )}
        </Panel>

        <div className="span-5 settings-side">
          <Panel title="Stream simulator" subtitle="Default ingestion source when Kafka is absent">
            {settings.data ? (
              <>
                <div className="tps-display">
                  <div>
                    <span>Target throughput</span>
                    <strong>{tps.toFixed(1)} <small>tps</small></strong>
                  </div>
                  <div className="tps-live">
                    <span className="pulse-dot ok" />
                    {system.data?.ingest.running ? "running" : "idle"}
                  </div>
                </div>
                <input
                  className="range"
                  type="range"
                  min={0.2}
                  max={60}
                  step={0.1}
                  value={tps}
                  onChange={(event) => update("simulator_tps", Number(event.target.value))}
                  aria-label="Simulator transactions per second"
                />
                <div className="range-scale"><span>0.2 tps</span><span>30</span><span>60 tps</span></div>
                <p className="field-hint">
                  Throughput changes apply after saving. The current process has emitted{" "}
                  {formatNumber(system.data?.ingest.emitted ?? 0)} events.
                </p>

                <div className="burst-grid">
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => burst("card_testing", 10, "Card-testing burst")}
                    disabled={busyPattern !== null}
                  >
                    <ZapIcon size={13} /> Card testing
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => burst("account_takeover", 3, "Account takeover")}
                    disabled={busyPattern !== null}
                  >
                    Account takeover
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => burst("stolen_card", 3, "Stolen card")}
                    disabled={busyPattern !== null}
                  >
                    Stolen card
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => burst("legit_high_value", 3, "Legitimate high-value")}
                    disabled={busyPattern !== null}
                  >
                    Hard negative
                  </button>
                </div>
              </>
            ) : (
              <Skeleton rows={6} />
            )}
          </Panel>

          <Panel title="Delivery" subtitle="Outbound notifications for blocked authorisations">
            {delivery ? (
              <div className="integration-list">
                <div>
                  <span className="integration-icon"><ShieldIcon size={15} /></span>
                  <div>
                    <strong>Telegram</strong>
                    <small>{delivery.telegram_configured ? "Bot token configured" : "Not configured"}</small>
                  </div>
                  <span className={`status-badge ${delivery.telegram_configured ? "resolved" : "open"}`}>
                    {delivery.telegram_configured ? "ready" : "off"}
                  </span>
                </div>
                <div>
                  <span className="integration-icon"><DatabaseIcon size={15} /></span>
                  <div>
                    <strong>Webhook</strong>
                    <small>{delivery.webhook_configured ? "Endpoint configured" : "No endpoint"}</small>
                  </div>
                  <span className={`status-badge ${delivery.webhook_configured ? "resolved" : "open"}`}>
                    {delivery.webhook_configured ? "ready" : "off"}
                  </span>
                </div>
                <div className="delivery-stats">
                  <span>sent <strong>{formatNumber(delivery.sent)}</strong></span>
                  <span>failed <strong>{formatNumber(delivery.failed)}</strong></span>
                  <span>throttled <strong>{formatNumber(delivery.skipped)}</strong></span>
                </div>
                <Toggle
                  checked={telegramEnabled}
                  onChange={(value) => update("telegram_enabled", value)}
                  label="Send notifications for blocked authorisations"
                />
                {telegramEnabled && !delivery.telegram_configured && !delivery.webhook_configured ? (
                  <p className="field-hint warn">
                    Notifications are enabled but no transport is configured. Set TELEGRAM_TOKEN and CHAT_ID.
                  </p>
                ) : null}
                {delivery.last_error ? <p className="inline-error">{delivery.last_error}</p> : null}
              </div>
            ) : (
              <Skeleton rows={5} />
            )}
          </Panel>
        </div>

        <Panel className="span-6" title="Operator identity" subtitle="Stored in this browser only">
          <div className="form-grid">
            <label className="field">
              <span>Operator handle</span>
              <input
                value={operator}
                onChange={(event) => setOperator(event.target.value)}
                placeholder="e.g. rina.analyst"
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>API key</span>
              <input
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="SENTINEL_API_KEY"
                autoComplete="off"
              />
            </label>
          </div>
          <p className="field-hint">
            The handle is sent as <code>X-Operator</code> and appears in the alert audit trail. The key is sent as{" "}
            <code>X-API-Key</code> and is only required when the server sets <code>SENTINEL_API_KEY</code>.
          </p>
          <div className="form-actions">
            <button className="btn btn-secondary" onClick={saveIdentity}>
              Save identity
            </button>
          </div>
        </Panel>

        <Panel className="span-6" title="Environment" subtitle="Runtime and storage">
          {system.data ? (
            <div className="env-grid">
              <div>
                <span>Service</span>
                <strong>{system.data.service.name}</strong>
                <small>v{system.data.service.version} · {system.data.service.environment}</small>
              </div>
              <div>
                <span>Database</span>
                <strong>{system.data.storage.engine}</strong>
                <small>{formatBytes(storage?.size_bytes)} on disk</small>
              </div>
              <div>
                <span>Model</span>
                <strong className="mono">{system.data.pipeline.model_version}</strong>
                <small>{formatNumber(system.data.pipeline.processed, true)} scored this process</small>
              </div>
              <div>
                <span>Uptime</span>
                <strong>{formatDuration(system.data.pipeline.uptime_seconds)}</strong>
                <small>retention {system.data.storage.retention_days} days</small>
              </div>
              <div>
                <span>Decision p50</span>
                <strong>{system.data.pipeline.latency.p50.toFixed(1)} ms</strong>
                <small>p95 {system.data.pipeline.latency.p95.toFixed(1)} ms</small>
              </div>
              <div>
                <span>Write queue</span>
                <strong>{formatNumber(system.data.pipeline.writer.queued)}</strong>
                <small>{formatNumber(system.data.pipeline.writer.written, true)} rows persisted</small>
              </div>
            </div>
          ) : (
            <Skeleton rows={6} />
          )}
          <div className="panel-foot inset">
            <span>Simulator: {formatPercent(1, 0)} synthetic · labels attached per event</span>
          </div>
        </Panel>

        <Panel
          className="span-12 danger-panel"
          title="Demo maintenance"
          subtitle="Destructive actions scoped to this environment"
        >
          <div className="danger-row">
            <div>
              <strong>Reset demo data</strong>
              <p>
                Deletes every transaction, alert, audit event and model registry row, then rebuilds seven days of
                history through the live scoring pipeline.
              </p>
            </div>
            <button className="btn btn-danger-ghost" onClick={resetDemo} disabled={resetting}>
              {resetting ? "Rebuilding…" : "Reset environment"}
            </button>
          </div>
          <div className="danger-row">
            <div>
              <strong>OpenAPI reference</strong>
              <p>Every endpoint used by this console is documented with request and response schemas.</p>
            </div>
            <a className="btn btn-secondary" href="/docs" target="_blank" rel="noreferrer">
              Open /docs
            </a>
          </div>
        </Panel>
      </div>
    </div>
  );
}
