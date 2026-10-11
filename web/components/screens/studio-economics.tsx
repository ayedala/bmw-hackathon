"use client";
import {useState, type FormEvent} from "react";
import {Button} from "@/components/ui/button";
import {callAdvisor} from "@/lib/advisor/client";
import type {AdvisorResult} from "@/lib/advisor/contracts";

const scenarios = ["Downside", "Base", "Upside"] as const;
const fields = [
  ["upfront_cost", "Development / tooling"], ["annual_fixed_cost", "Annual support cost"],
  ["baseline_units", "Existing annual sales"], ["incremental_units", "Added annual sales"],
  ["adoption_rate", "Adoption (0–1)"], ["revenue_per_extra_vehicle", "Revenue / added vehicle"],
  ["cost_per_extra_vehicle", "Vehicle cost / added vehicle"], ["revenue_uplift_per_adopter", "Feature revenue / existing adopter"],
  ["feature_cost_per_adopter", "Feature cost / equipped vehicle"],
] as const;
function Calculator({result}: {result: AdvisorResult}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [source, setSource] = useState("");
  const [discount, setDiscount] = useState("10");
  const [rows, setRows] = useState<Record<string, string | number>[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function calculate(event: FormEvent) {
    event.preventDefault(); setBusy(true); setRows([]); setError("");
    try {
      await callAdvisor("scenarios", {rows: scenarios.map(scenario => ({scenario, ...Object.fromEntries(fields.map(([field]) => [field, values[`${scenario}:${field}`] || null]))})),
        source, years: result.packet.request.planning_years, discount_rate: Number(discount) / 100}, event => {if (event.type === "scenarios") setRows(event.rows);});
    } catch (e) {setError(e instanceof Error ? e.message : "Scenario calculation failed.");} finally {setBusy(false);}
  }
  return <form onSubmit={calculate} className="space-y-3"><p className="text-xs leading-relaxed text-slate-500">Enter sourced estimates or label them as hypothetical. Blank values remain unknown. Currency: {result.packet.request.currency}; horizon: {result.packet.request.planning_years} years.</p>
    <div className="overflow-x-auto"><table className="w-full min-w-[480px] text-left text-xs"><thead><tr><th className="py-2 font-medium">Assumption</th>{scenarios.map(s => <th key={s} className="px-1 font-medium">{s}</th>)}</tr></thead><tbody>{fields.map(([field, label]) => <tr key={field} className="border-t border-slate-100"><th className="py-2 pr-2 font-normal text-slate-600">{label}</th>{scenarios.map(scenario => <td key={scenario} className="px-1"><input className="w-full min-w-20 rounded-sm border border-slate-200 px-2 py-1" aria-label={`${scenario}: ${label}`} type="number" min={0} max={field === "adoption_rate" ? 1 : undefined}
      step={field.endsWith("units") ? 1 : "any"} required value={values[`${scenario}:${field}`] ?? ""} onChange={e => {setValues({...values, [`${scenario}:${field}`]: e.target.value}); setRows([]);}} /></td>)}</tr>)}</tbody></table></div>
    <label className="block text-xs">Estimate source / owner<input className="mt-1 block w-full rounded-md border border-slate-200 px-2 py-2" required maxLength={500} value={source} onChange={e => {setSource(e.target.value); setRows([]);}} placeholder="Source and owner, or hypothetical scenario" /></label>
    <label className="block text-xs">Discount rate (%) · scenario assumption<input className="ml-2 w-20 rounded-md border border-slate-200 px-2 py-1" type="number" min={0} max={99} step="any" required value={discount} onChange={e => {setDiscount(e.target.value); setRows([]);}} /></label>
    <Button type="submit" disabled={busy}>{busy ? "Calculating…" : "Calculate scenarios"}</Button>
    {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
    {rows.length > 0 && <div className="overflow-auto"><table className="w-full text-left text-xs"><thead><tr>{["Scenario", "Annual added revenue", "Annual net cash flow", "NPV"].map(k => <th key={k} className="p-2 font-medium">{k}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i} className="border-t border-slate-200">{["Scenario", "Annual added revenue", "Annual net cash flow", "NPV"].map(k => <td key={k} className="p-2 tabular-nums">{typeof row[k] === "number" ? row[k].toLocaleString(undefined, {maximumFractionDigits: 2}) : row[k]}</td>)}</tr>)}</tbody></table><p className="mt-2 text-2xs text-slate-500">Conditional scenarios, not forecasts or approvals. Annual assumptions repeat across the horizon; NPV discounts cash flows and deducts upfront cost.</p></div>}
  </form>;
}
export function StudioEconomics({result}: {result: AdvisorResult}) {
  const [option, setOption] = useState(result.report.options[0]?.option_id || "");
  return <section className="space-y-3 border-t border-slate-200 pt-4"><h3 className="text-sm font-semibold">Test the business case</h3><label className="block text-xs">Idea to model<select className="ml-2 rounded-md border border-slate-200 px-2 py-1" value={option} onChange={e => setOption(e.target.value)}>{result.report.options.map(o => <option key={o.option_id} value={o.option_id}>{o.title}</option>)}</select></label><Calculator key={option} result={result} /></section>;
}
