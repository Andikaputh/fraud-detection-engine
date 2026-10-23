import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { api } from "../lib/api";
import { operatorName } from "../lib/hooks";
import { useLive } from "../lib/LiveContext";
import { useToast } from "./Toast";
import {
  CommandIcon,
  MenuIcon,
  SearchIcon,
  ZapIcon,
} from "./icons";

const TITLES: Record<string, { title: string; crumb: string }> = {
  "/": { title: "Overview", crumb: "Monitor" },
  "/alerts": { title: "Alert queue", crumb: "Monitor" },
  "/analytics": { title: "Analytics", crumb: "Insight" },
  "/model": { title: "Model", crumb: "Insight" },
  "/settings": { title: "Settings", crumb: "Operations" },
};

function UtcClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <span className="utc-clock" title="Coordinated Universal Time">
      {now.toISOString().slice(11, 19)} UTC
    </span>
  );
}

export function Topbar({
  onMenu,
  onPalette,
}: {
  onMenu: () => void;
  onPalette: () => void;
}) {
  const location = useLocation();
  const meta = TITLES[location.pathname] || { title: "Not found", crumb: "Console" };
  const live = useLive();
  const toast = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const fire = async (pattern: string, count: number, label: string) => {
    setBusy(true);
    setMenuOpen(false);
    try {
      const result = await api.burst(pattern, count);
      toast.push(`${label} simulated`, {
        message: `${result.accepted} authorisations processed in ${result.elapsed_ms} ms.`,
        tone: "success",
      });
    } catch (error) {
      toast.push("Simulation failed", {
        message: error instanceof Error ? error.message : "Unknown error",
        tone: "error",
      });
    } finally {
      setBusy(false);
    }
  };

  const initials = operatorName()
    .split(/[.\s_-]/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "OP";

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="icon-button menu-button" onClick={onMenu} aria-label="Open navigation">
          <MenuIcon size={18} />
        </button>
        <div className="crumbs">
          <span>{meta.crumb}</span>
          <span className="crumb-sep">/</span>
          <strong>{meta.title}</strong>
        </div>
      </div>

      <div className="topbar-right">
        <UtcClock />
        <span className={`live-pill ${live.connection === "live" ? "is-live" : ""}`}>
          <span className={`pulse-dot ${live.connection === "live" ? "ok" : "warn"}`} />
          {live.connection === "live" ? "Live" : live.connection}
        </span>

        <button className="palette-trigger" onClick={onPalette}>
          <SearchIcon size={14} />
          <span>Search</span>
          <kbd>
            <CommandIcon size={11} />K
          </kbd>
        </button>

        <div className="simulate-wrap" ref={menuRef}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setMenuOpen((value) => !value)}
            disabled={busy}
          >
            <ZapIcon size={14} />
            {busy ? "Simulating" : "Simulate"}
          </button>
          {menuOpen ? (
            <div className="popover simulate-menu">
              <p className="popover-label">Inject test traffic</p>
              <button onClick={() => fire("card_testing", 10, "Card-testing burst")}>
                <span>
                  <strong>Card testing</strong>
                  <small>10 low-value attempts in 30s</small>
                </span>
                <span className="kbd-hint">CT</span>
              </button>
              <button onClick={() => fire("account_takeover", 3, "Account takeover")}>
                <span>
                  <strong>Account takeover</strong>
                  <small>New device, foreign IP, high value</small>
                </span>
                <span className="kbd-hint">ATO</span>
              </button>
              <button onClick={() => fire("stolen_card", 3, "Stolen card")}>
                <span>
                  <strong>Stolen card</strong>
                  <small>Risky merchant, 8-48M IDR</small>
                </span>
                <span className="kbd-hint">CNP</span>
              </button>
            </div>
          ) : null}
        </div>

        <div className="avatar" title={operatorName()}>
          {initials}
        </div>
      </div>
    </header>
  );
}
