import { useState } from "react";

import { formatDate, formatNumber, formatTime } from "../lib/format";
import type { SeriesPoint } from "../types";

const COLORS = {
  blue: "#6d9eff",
  green: "#3ddc97",
  amber: "#f5b544",
  red: "#ff6b6b",
  violet: "#a78bfa",
  slate: "#64748b",
};

function niceMax(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 4;
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  const normalized = value / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

export interface ChartSeries {
  key: keyof SeriesPoint;
  label: string;
  color: string;
  area?: boolean;
}

export function ChartLegend({ series }: { series: ChartSeries[] }) {
  return (
    <div className="chart-legend">
      {series.map((item) => (
        <span key={String(item.key)}>
          <span className="legend-swatch" style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

export function AreaChart({
  data,
  series,
  height = 250,
  xMode = "time",
  yFormat = (value: number) => formatNumber(value, true),
}: {
  data: SeriesPoint[];
  series: ChartSeries[];
  height?: number;
  xMode?: "time" | "date";
  yFormat?: (value: number) => string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const width = 760;
  const pad = { left: 46, right: 14, top: 14, bottom: 28 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const maxValue = niceMax(
    Math.max(
      1,
      ...data.flatMap((row) => series.map((item) => Number(row[item.key]) || 0)),
    ),
  );
  const count = Math.max(data.length, 2);
  const x = (index: number) => pad.left + (index * innerW) / (count - 1);
  const y = (value: number) => pad.top + innerH * (1 - value / maxValue);

  const linePath = (key: keyof SeriesPoint) =>
    data
      .map((row, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(Number(row[key]) || 0).toFixed(2)}`)
      .join(" ");

  const areaPath = (key: keyof SeriesPoint) => {
    if (data.length === 0) return "";
    const line = linePath(key);
    return `${line} L${x(data.length - 1).toFixed(2)},${(pad.top + innerH).toFixed(2)} L${x(0).toFixed(2)},${(pad.top + innerH).toFixed(2)} Z`;
  };

  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const labelIndexes = Array.from(new Set([0, Math.floor((count - 1) * 0.25), Math.floor((count - 1) * 0.5), Math.floor((count - 1) * 0.75), count - 1])).filter(
    (index) => index >= 0 && index < data.length,
  );
  const point = active !== null ? data[active] : null;

  return (
    <div className="chart">
      <ChartLegend series={series} />
      <div className="chart-canvas">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="chart-svg"
          role="img"
          aria-label="Transaction volume over time"
          onMouseLeave={() => setActive(null)}
          onMouseMove={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            const relative = ((event.clientX - rect.left) / rect.width) * width;
            const index = Math.round(((relative - pad.left) / innerW) * (count - 1));
            setActive(Math.min(Math.max(index, 0), data.length - 1));
          }}
        >
          <defs>
            {series.map((item) => (
              <linearGradient id={`fill-${String(item.key)}`} key={String(item.key)} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={item.color} stopOpacity="0.22" />
                <stop offset="100%" stopColor={item.color} stopOpacity="0" />
              </linearGradient>
            ))}
          </defs>
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={pad.top + innerH * (1 - tick)}
                y2={pad.top + innerH * (1 - tick)}
                stroke="#1d222a"
                strokeDasharray={tick === 0 ? "0" : "3 4"}
              />
              <text x={pad.left - 8} y={pad.top + innerH * (1 - tick) + 3.5} textAnchor="end" className="axis-label">
                {yFormat(maxValue * tick)}
              </text>
            </g>
          ))}
          {series
            .filter((item) => item.area)
            .map((item) => (
              <path d={areaPath(item.key)} fill={`url(#fill-${String(item.key)})`} key={`area-${String(item.key)}`} />
            ))}
          {series.map((item) => (
            <path
              key={String(item.key)}
              d={linePath(item.key)}
              fill="none"
              stroke={item.color}
              strokeWidth={1.8}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}
          {point && active !== null ? (
            <g>
              <line x1={x(active)} x2={x(active)} y1={pad.top} y2={pad.top + innerH} stroke="#39404b" strokeWidth="1" />
              {series.map((item) => (
                <circle
                  key={String(item.key)}
                  cx={x(active)}
                  cy={y(Number(point[item.key]) || 0)}
                  r={3}
                  fill="#0e1116"
                  stroke={item.color}
                  strokeWidth={2}
                />
              ))}
            </g>
          ) : null}
          {labelIndexes.map((index) => (
            <text key={index} x={x(index)} y={height - 8} textAnchor="middle" className="axis-label">
              {xMode === "date" ? formatDate(data[index].t) : formatTime(data[index].t)}
            </text>
          ))}
        </svg>
        {point && active !== null ? (
          <div
            className="chart-tooltip"
            style={{
              left: `${Math.min(Math.max((x(active) / width) * 100, 12), 88)}%`,
            }}
          >
            <p className="tooltip-time">{xMode === "date" ? formatDate(point.t) : formatTime(point.t)}</p>
            {series.map((item) => (
              <div className="tooltip-row" key={String(item.key)}>
                <span>
                  <span className="legend-swatch" style={{ background: item.color }} />
                  {item.label}
                </span>
                <strong>{formatNumber(Number(point[item.key]) || 0)}</strong>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function Sparkline({
  values,
  color = COLORS.blue,
  width = 96,
  height = 30,
}: {
  values: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (values.length === 0) return <svg width={width} height={height} aria-hidden="true" />;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const points = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - 2 - ((value - min) / range) * (height - 6);
    return [x, y] as const;
  });
  const line = points.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const gradientId = `spark-${color.replace("#", "")}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="sparkline">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Donut({
  segments,
  total,
  centerLabel,
  size = 148,
}: {
  segments: { label: string; value: number; color: string }[];
  total: number;
  centerLabel: string;
  size?: number;
}) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="donut-wrap" style={{ width: size }}>
      <svg viewBox="0 0 140 140" width={size} height={size} role="img" aria-label={centerLabel}>
        <circle cx="70" cy="70" r={radius} fill="none" stroke="#1a1f27" strokeWidth="11" />
        {segments.map((segment) => {
          const share = total > 0 ? segment.value / total : 0;
          const length = Math.max(share * circumference - 3, 0);
          const dashOffset = -offset;
          offset += share * circumference;
          return (
            <circle
              key={segment.label}
              cx="70"
              cy="70"
              r={radius}
              fill="none"
              stroke={segment.color}
              strokeWidth="11"
              strokeDasharray={`${length} ${circumference - length}`}
              strokeDashoffset={dashOffset}
              strokeLinecap="butt"
              transform="rotate(-90 70 70)"
            />
          );
        })}
      </svg>
      <div className="donut-center">
        <strong>{formatNumber(total, true)}</strong>
        <span>{centerLabel}</span>
      </div>
    </div>
  );
}

export function StackedBars({ data }: { data: SeriesPoint[] }) {
  const max = Math.max(1, ...data.map((point) => point.total));
  return (
    <div className="stacked-bars" role="img" aria-label="Decision mix over time">
      {data.map((point) => {
        const height = Math.max((point.total / max) * 100, point.total > 0 ? 2 : 0);
        const allowShare = point.total ? (point.total - point.blocked - point.review) / point.total : 0;
        return (
          <div className="stacked-column" key={point.t}>
            <div
              className="stacked-bar"
              style={{ height: `${height}%` }}
              title={`${formatTime(point.t)} · ${point.total} total · ${point.blocked} blocked · ${point.review} review`}
            >
              <span className="seg-block" style={{ flexGrow: point.blocked }} />
              <span className="seg-review" style={{ flexGrow: point.review }} />
              <span className="seg-allow" style={{ flexGrow: Math.max(allowShare * point.total, 0) }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function HBarList({
  items,
  formatValue = (value: number) => formatNumber(value),
  color = COLORS.blue,
}: {
  items: { label: string; value: number; meta?: string }[];
  formatValue?: (value: number) => string;
  color?: string;
}) {
  if (items.length === 0) return <p className="muted-text">No data for this period.</p>;
  const max = Math.max(...items.map((item) => item.value), 1);
  return (
    <div className="hbar-list">
      {items.map((item) => (
        <div className="hbar-row" key={item.label}>
          <div className="hbar-label">
            <span>{item.label}</span>
            <span className="hbar-value">
              {formatValue(item.value)}
              {item.meta ? <em>{item.meta}</em> : null}
            </span>
          </div>
          <div className="hbar-track">
            <span style={{ width: `${Math.max((item.value / max) * 100, 2)}%`, background: color }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function RiskGauge({ score, size = 190 }: { score: number; size?: number }) {
  const value = Math.min(Math.max(score, 0), 100);
  const color = value >= 80 ? COLORS.red : value >= 55 ? COLORS.amber : value >= 30 ? "#e9c46a" : COLORS.green;
  const label = value >= 80 ? "High risk" : value >= 55 ? "Elevated" : value >= 30 ? "Watch" : "Low risk";
  // The arc is a semicircle centred at (60, 62) with radius 50. Place the
  // endpoint marker on that arc instead of interpolating along the baseline.
  const angle = Math.PI * (1 - value / 100);
  const markerX = 60 + 50 * Math.cos(angle);
  const markerY = 62 - 50 * Math.sin(angle);
  return (
    <div className="gauge" style={{ width: size }}>
      <svg viewBox="0 0 120 74" width={size} height={size * 0.616} role="img" aria-label={`Risk score ${value} of 100`}>
        <path d="M10 62 A 50 50 0 0 1 110 62" fill="none" stroke="#1b2028" strokeWidth="9" strokeLinecap="round" pathLength={100} />
        <path
          d="M10 62 A 50 50 0 0 1 110 62"
          fill="none"
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray={`${Math.max(value, 1)} 100`}
          style={{ transition: "stroke-dasharray 400ms ease" }}
        />
        <circle cx={markerX} cy={markerY} r="3.6" fill="#0e1116" stroke={color} strokeWidth="2.4" />
      </svg>
      <div className="gauge-center">
        <strong style={{ color }}>{value}</strong>
        <span>{label}</span>
      </div>
      <div className="gauge-scale">
        <span>0</span>
        <span>100</span>
      </div>
    </div>
  );
}

export const CHART_COLORS = COLORS;
