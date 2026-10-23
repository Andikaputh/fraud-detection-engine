import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { STREAM_URL } from "../lib/api";
import type { TransactionSummary } from "../types";
import { useToast } from "../components/Toast";

type Connection = "connecting" | "live" | "reconnecting" | "offline";

interface LiveAlert {
  id: string;
  transaction_id: string;
  severity: "critical" | "high" | "medium";
  risk_score: number;
  merchant_name: string;
  amount: number;
  customer_id: string;
  created_at: string;
}

interface LiveContextValue {
  transactions: TransactionSummary[];
  connection: Connection;
  paused: boolean;
  setPaused: (paused: boolean) => void;
  received: number;
  latestAlert: LiveAlert | null;
  alertCount: number;
  clear: () => void;
}

const LiveContext = createContext<LiveContextValue | null>(null);

const MAX_ITEMS = 120;

export function LiveProvider({ children }: { children: ReactNode }) {
  const [transactions, setTransactions] = useState<TransactionSummary[]>([]);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [paused, setPausedState] = useState(false);
  const [received, setReceived] = useState(0);
  const [latestAlert, setLatestAlert] = useState<LiveAlert | null>(null);
  const [alertCount, setAlertCount] = useState(0);
  const [generation, setGeneration] = useState(0);

  const pending = useRef<TransactionSummary[]>([]);
  const seen = useRef(new Set<string>());
  const pausedRef = useRef(false);
  const lastToastAt = useRef(0);
  const toast = useToast();

  const setPaused = useCallback((value: boolean) => {
    pausedRef.current = value;
    setPausedState(value);
  }, []);

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: number | undefined;
    let closed = false;

    const connect = () => {
      source = new EventSource(STREAM_URL);

      source.addEventListener("open", () => {
        setConnection("live");
      });

      source.addEventListener("ready", () => {
        setConnection("live");
      });

      source.addEventListener("transaction", (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent).data) as { data: TransactionSummary };
          const data = payload.data;
          if (!data?.id || seen.current.has(data.id)) return;
          seen.current.add(data.id);
          if (seen.current.size > 4000) {
            const trimmed = Array.from(seen.current).slice(-1500);
            seen.current = new Set(trimmed);
          }
          pending.current.push({ ...data, label: data.label ?? null });
          setReceived((value) => value + 1);
        } catch {
          /* ignore malformed frame */
        }
      });

      source.addEventListener("alert", (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent).data) as { data: LiveAlert };
          if (!payload.data) return;
          setLatestAlert(payload.data);
          setAlertCount((value) => value + 1);
          const now = Date.now();
          if (payload.data.severity !== "medium" && now - lastToastAt.current >= 8_000) {
            lastToastAt.current = now;
            toast.push(
              payload.data.severity === "critical" ? "Critical alert raised" : "High-risk alert",
              {
                message: `${payload.data.merchant_name} · Rp ${Math.round(payload.data.amount).toLocaleString("en-US")}`,
                tone: payload.data.severity === "critical" ? "error" : "info",
              },
            );
          }
        } catch {
          /* ignore malformed frame */
        }
      });

      source.addEventListener("error", () => {
        if (closed) return;
        setConnection((current) => (current === "live" ? "reconnecting" : "offline"));
        source?.close();
        retry = window.setTimeout(() => {
          if (!closed) {
            setConnection("reconnecting");
            connect();
          }
        }, 4000);
      });
    };

    connect();

    const flush = window.setInterval(() => {
      if (pending.current.length === 0) return;
      if (pausedRef.current) return;
      const batch = pending.current.splice(0, pending.current.length);
      setTransactions((current) => [...batch.reverse(), ...current].slice(0, MAX_ITEMS));
    }, 280);

    return () => {
      closed = true;
      source?.close();
      if (retry) window.clearTimeout(retry);
      window.clearInterval(flush);
    };
  }, [generation, toast]);

  const clear = useCallback(() => {
    pending.current = [];
    setTransactions([]);
    setPaused(false);
    setGeneration((value) => value + 1);
  }, [setPaused]);

  const value = useMemo(
    () => ({ transactions, connection, paused, setPaused, received, latestAlert, alertCount, clear }),
    [transactions, connection, paused, setPaused, received, latestAlert, alertCount, clear],
  );

  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveContextValue {
  const context = useContext(LiveContext);
  if (!context) throw new Error("useLive must be used inside LiveProvider");
  return context;
}
