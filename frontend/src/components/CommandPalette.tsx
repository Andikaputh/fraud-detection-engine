import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { useLive } from "../lib/LiveContext";
import { useToast } from "./Toast";
import {
  BellIcon,
  ChartIcon,
  CpuIcon,
  ExternalLinkIcon,
  GridIcon,
  PauseIcon,
  PlayIcon,
  SearchIcon,
  SettingsIcon,
  ZapIcon,
} from "./icons";

interface Command {
  id: string;
  label: string;
  hint: string;
  group: "Navigate" | "Actions";
  icon: typeof GridIcon;
  run: () => void;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const live = useLive();
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      window.setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const go = (path: string) => {
    navigate(path);
    onClose();
  };

  const burst = async () => {
    onClose();
    try {
      const result = await api.burst("card_testing", 8);
      toast.push("Card-testing burst simulated", {
        message: `${result.accepted} authorisations processed.`,
        tone: "success",
      });
    } catch (error) {
      toast.push("Simulation failed", {
        message: error instanceof Error ? error.message : "Unknown error",
        tone: "error",
      });
    }
  };

  const commands = useMemo<Command[]>(
    () => [
      { id: "nav-overview", label: "Go to Overview", hint: "G O", group: "Navigate", icon: GridIcon, run: () => go("/") },
      { id: "nav-alerts", label: "Go to Alert queue", hint: "G A", group: "Navigate", icon: BellIcon, run: () => go("/alerts") },
      { id: "nav-analytics", label: "Go to Analytics", hint: "G N", group: "Navigate", icon: ChartIcon, run: () => go("/analytics") },
      { id: "nav-model", label: "Go to Model", hint: "G M", group: "Navigate", icon: CpuIcon, run: () => go("/model") },
      { id: "nav-settings", label: "Go to Settings", hint: "G S", group: "Navigate", icon: SettingsIcon, run: () => go("/settings") },
      {
        id: "act-live",
        label: live.paused ? "Resume live stream" : "Pause live stream",
        hint: "Space",
        group: "Actions",
        icon: live.paused ? PlayIcon : PauseIcon,
        run: () => {
          live.setPaused(!live.paused);
          toast.push(live.paused ? "Live stream resumed" : "Live stream paused", { tone: "info" });
          onClose();
        },
      },
      {
        id: "act-burst",
        label: "Simulate card-testing burst",
        hint: "10 txns",
        group: "Actions",
        icon: ZapIcon,
        run: burst,
      },
      {
        id: "act-docs",
        label: "Open API reference",
        hint: "/docs",
        group: "Actions",
        icon: ExternalLinkIcon,
        run: () => {
          window.open("/docs", "_blank", "noopener");
          onClose();
        },
      },
    ],
    [live, onClose, toast],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((command) => `${command.label} ${command.group}`.toLowerCase().includes(needle));
  }, [commands, query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelected((value) => Math.min(value + 1, Math.max(filtered.length - 1, 0)));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelected((value) => Math.max(value - 1, 0));
      } else if (event.key === "Enter") {
        event.preventDefault();
        filtered[selected]?.run();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered, selected, onClose]);

  if (!open) return null;

  let lastGroup = "";

  return (
    <div className="palette-overlay" onMouseDown={onClose} role="presentation">
      <div className="palette" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-label="Command palette">
        <div className="palette-input">
          <SearchIcon size={16} />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setSelected(0);
            }}
            placeholder="Search pages and actions…"
            aria-label="Search commands"
          />
          <kbd>esc</kbd>
        </div>
        <div className="palette-list">
          {filtered.length === 0 ? <p className="palette-empty">No commands match “{query}”.</p> : null}
          {filtered.map((command, index) => {
            const showGroup = command.group !== lastGroup;
            lastGroup = command.group;
            return (
              <div key={command.id}>
                {showGroup ? <p className="palette-group">{command.group}</p> : null}
                <button
                  className={`palette-item ${index === selected ? "is-selected" : ""}`}
                  onMouseEnter={() => setSelected(index)}
                  onClick={command.run}
                >
                  <command.icon size={15} />
                  <span>{command.label}</span>
                  <span className="palette-hint">{command.hint}</span>
                </button>
              </div>
            );
          })}
        </div>
        <div className="palette-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> select</span>
          <span>Sentinel console</span>
        </div>
      </div>
    </div>
  );
}
