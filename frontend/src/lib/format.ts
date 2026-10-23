const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export function formatIDR(value: number, compactValue = true): string {
  if (!Number.isFinite(value)) return "N/A";
  return `Rp ${compactValue ? compact.format(value) : integer.format(value)}`;
}

export function formatNumber(value: number, compactValue = false): string {
  if (!Number.isFinite(value)) return "N/A";
  return compactValue ? compact.format(value) : integer.format(value);
}

export function formatDecimal(value: number): string {
  return Number.isFinite(value) ? decimal.format(value) : "N/A";
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "N/A";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDelta(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "N/A";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

const UTC = "UTC";

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "N/A";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "N/A";
  return date.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: UTC,
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "N/A";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "N/A";
  return date.toLocaleString("en-GB", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: UTC,
  });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "N/A";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "N/A";
  return date.toLocaleDateString("en-GB", { month: "short", day: "numeric", timeZone: UTC });
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "N/A";
  const date = new Date(iso).getTime();
  if (Number.isNaN(date)) return "N/A";
  const seconds = Math.max(0, Math.round((now - date) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes < 0) return "N/A";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function shortId(value: string, length = 10): string {
  if (!value) return "N/A";
  const prefix = value.includes("_") ? `${value.split("_")[0]}_` : "";
  const body = value.slice(prefix.length);
  return `${prefix}${body.slice(0, length)}`;
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}
