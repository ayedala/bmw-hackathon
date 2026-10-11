"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface BalanceDatum {
  topic: string;
  Supporting: number;
  Contradicting: number;
  Neutral: number;
}

const tooltipClass = {
  contentStyle: { border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 12, padding: "6px 8px", boxShadow: "none" },
  labelStyle: { color: "#09090b", fontWeight: 500, marginBottom: 2 },
  itemStyle: { padding: 0 },
};

/** Evidence balance per topic. Recharts requires style objects for its own tooltip; no inline styles are used in app markup. */
export function EvidenceBalanceChart({ data }: { data: BalanceDatum[] }) {
  return (
    <div className="h-48 w-full" role="img" aria-label="Supporting, contradicting and neutral evidence per topic">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, bottom: 0, left: 0 }} barCategoryGap={8}>
          <CartesianGrid horizontal={false} stroke="#f1f5f9" />
          <XAxis type="number" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="topic" width={92} tick={{ fontSize: 11, fill: "#334155" }} axisLine={false} tickLine={false} />
          <Tooltip cursor={{ fill: "#f8fafc" }} {...tooltipClass} />
          <Bar dataKey="Supporting" stackId="a" fill="#27272a" />
          <Bar dataKey="Contradicting" stackId="a" fill="#f59e0b" />
          <Bar dataKey="Neutral" stackId="a" fill="#cbd5e1" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export interface DistributionDatum {
  band: string;
  count: number;
}

export function ScoreDistributionChart({ data }: { data: DistributionDatum[] }) {
  return (
    <div className="h-36 w-full" role="img" aria-label="Requirements by legacy planning priority band">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
          <CartesianGrid vertical={false} stroke="#f1f5f9" />
          <XAxis dataKey="band" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip cursor={{ fill: "#f8fafc" }} {...tooltipClass} />
          <Bar dataKey="count" name="Requirements" fill="#27272a" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
