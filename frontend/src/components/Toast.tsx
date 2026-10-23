import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type Tone = "success" | "error" | "info";

interface ToastItem {
  id: number;
  title: string;
  message?: string;
  tone: Tone;
}

interface ToastContextValue {
  push: (title: string, options?: { message?: string; tone?: Tone }) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((title: string, options?: { message?: string; tone?: Tone }) => {
    const id = Date.now() + Math.random();
    setItems((current) => [...current.slice(-3), { id, title, message: options?.message, tone: options?.tone || "info" }]);
    window.setTimeout(() => {
      setItems((current) => current.filter((item) => item.id !== id));
    }, 5200);
  }, []);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-viewport" role="status" aria-live="polite">
        {items.map((item) => (
          <div className={`toast toast-${item.tone}`} key={item.id}>
            <span className="toast-dot" />
            <div>
              <p className="toast-title">{item.title}</p>
              {item.message ? <p className="toast-message">{item.message}</p> : null}
            </div>
            <button
              className="toast-close"
              onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}
              aria-label="Dismiss notification"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
