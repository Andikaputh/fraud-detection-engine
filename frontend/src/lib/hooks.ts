import { useCallback, useEffect, useRef, useState } from "react";

interface ResourceState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
  updatedAt: number | null;
}

export function useResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  key: string,
  intervalMs = 0,
  enabled = true,
): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let controller: AbortController | null = null;
    let timer: number | undefined;

    if (!enabled) {
      setLoading(false);
      setError(null);
      return;
    }

    const run = async (initial: boolean) => {
      controller = new AbortController();
      if (initial) setLoading(true);
      try {
        const result = await loaderRef.current(controller.signal);
        if (!cancelled) {
          setData(result);
          setError(null);
          setUpdatedAt(Date.now());
        }
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        setError(err instanceof Error ? err.message : "Request failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run(true);
    if (intervalMs > 0) {
      timer = window.setInterval(() => {
        if (document.visibilityState === "visible") void run(false);
      }, intervalMs);
    }

    return () => {
      cancelled = true;
      controller?.abort();
      if (timer) window.clearInterval(timer);
    };
  }, [key, intervalMs, nonce, enabled]);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);
  return { data, error, loading, refresh, updatedAt };
}

export function useTicker(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}

export function operatorName(): string {
  return localStorage.getItem("sentinel.operator") || "operator";
}
