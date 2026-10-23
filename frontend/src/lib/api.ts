import type {
  Alert,
  AlertPage,
  AlertStats,
  Analytics,
  EngineSettings,
  ModelInfo,
  Overview,
  Transaction,
  TransactionPage,
  WhatIfResult,
  WindowKey,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "";
const ROOT = `${API_BASE}/api/v1`;
export const STREAM_URL = `${ROOT}/stream`;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const operator = localStorage.getItem("sentinel.operator");
  const key = localStorage.getItem("sentinel.apiKey");
  if (operator) headers["X-Operator"] = operator;
  if (key) headers["X-API-Key"] = key;
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${ROOT}${path}`, {
    ...init,
    signal,
    headers: { ...authHeaders(), ...(init.headers || {}) },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((item: { msg?: string }) => item.msg).join(", ");
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

export const api = {
  overview: (window: WindowKey, signal?: AbortSignal) =>
    request<Overview>(`/overview${query({ window })}`, {}, signal),

  analytics: (window: WindowKey, signal?: AbortSignal) =>
    request<Analytics>(`/analytics${query({ window })}`, {}, signal),

  transactions: (
    params: {
      page?: number;
      page_size?: number;
      decision?: string;
      window?: string;
      search?: string;
      min_risk?: number;
      label?: string;
      sort_by?: string;
    },
    signal?: AbortSignal,
  ) => request<TransactionPage>(`/transactions${query(params)}`, {}, signal),

  transaction: (id: string, signal?: AbortSignal) =>
    request<{ transaction: Transaction; alert: Alert | null }>(`/transactions/${id}`, {}, signal),

  alerts: (
    params: {
      page?: number;
      page_size?: number;
      status?: string;
      severity?: string;
      window?: string;
      search?: string;
      min_risk?: number;
      sort_by?: string;
    },
    signal?: AbortSignal,
  ) => request<AlertPage>(`/alerts${query(params)}`, {}, signal),

  alert: (id: string, signal?: AbortSignal) => request<Alert>(`/alerts/${id}`, {}, signal),

  alertStats: (signal?: AbortSignal) => request<AlertStats>("/alerts/stats", {}, signal),

  updateAlert: (id: string, body: { status?: string; assignee?: string | null; note?: string }) =>
    request<Alert>(`/alerts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  system: (signal?: AbortSignal) =>
    request<import("../types").SystemStatus>("/system", {}, signal),

  backfill: (signal?: AbortSignal) =>
    request<import("../types").BackfillStatus>("/backfill", {}, signal),

  settings: (signal?: AbortSignal) => request<EngineSettings>("/settings", {}, signal),

  updateSettings: (body: Partial<EngineSettings>) =>
    request<EngineSettings>("/settings", { method: "PATCH", body: JSON.stringify(body) }),

  model: (signal?: AbortSignal) => request<ModelInfo>("/model", {}, signal),

  whatIf: (body: {
    amount: number;
    merchant_category: string;
    merchant_country: string;
    ip_country: string;
    channel: string;
    new_customer: boolean;
    hour?: number;
  }) => request<WhatIfResult>("/model/score", { method: "POST", body: JSON.stringify(body) }),

  burst: (pattern: string, count: number) =>
    request<{ accepted: number; pattern: string; elapsed_ms: number }>("/simulate/burst", {
      method: "POST",
      body: JSON.stringify({ pattern, count }),
    }),

  resetDemo: () =>
    request<{ status: string; transactions?: number; alerts?: number }>("/demo/reset", { method: "POST" }),

  health: (signal?: AbortSignal) =>
    request<{ status: string; version: string; database: string }>("/health", {}, signal),
};
