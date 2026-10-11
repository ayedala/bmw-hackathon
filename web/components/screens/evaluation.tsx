"use client";

import {useCallback, useEffect, useState} from "react";
import {PageHeader} from "@/components/app/layout-parts";
import {Button} from "@/components/ui/button";
import {callAdvisor} from "@/lib/advisor/client";
import type {EvaluationSignal, EvaluationSnapshot} from "@/lib/advisor/contracts";
import {fieldClass, labelClass} from "./decision-studio";

type Role = "primary" | "secondary" | "adjudicator";
type Draft = EvaluationSignal;
const splits = ["development", "heldout_g60", "transfer_f70", "transfer_g70"];
const splitLabels: Record<string, string> = {development: "5 Series · development", heldout_g60: "5 Series · held out",
  transfer_f70: "1 Series · transfer", transfer_g70: "7 Series · transfer"};
const domains = ["controls_usability", "software_reliability", "charging_and_range", "ride_and_comfort",
  "noise_and_refinement", "storage_and_practicality", "driver_assistance", "other"];
const emptySignal = (): Draft => ({need_domain: "", atomic_claim: "", customer_outcome: "",
  polarity: "complaint", evidence_text: "", use_context: "", uncertainties: []});

export function EvaluationScreen() {
  const [snapshot, setSnapshot] = useState<EvaluationSnapshot | null>(null);
  const [role, setRole] = useState<Role>("primary");
  const [reviewer, setReviewer] = useState("");
  const [signals, setSignals] = useState<Draft[]>([emptySignal()]);
  const [abstention, setAbstention] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("all");

  const load = useCallback(async (nextRole: Role, recordId?: string) => {
    setBusy(true); setError(""); setNotice("");
    try {
      await callAdvisor("evaluation", {action: "summary", role: nextRole, record_id: recordId}, event => {
        if (event.type === "evaluation") setSnapshot(event.evaluation);
      });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Evaluation could not load."); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { void load("primary"); }, [load]);

  const active = snapshot?.case;
  useEffect(() => {
    const label = role === "adjudicator" ? active?.primary?.adjudication : active?.review;
    setReviewer(label?.reviewer_id || "");
    setSignals(label?.signals?.length ? label.signals.map(row => ({...row})) : [emptySignal()]);
    setAbstention(label?.abstention_reason || "");
    setDifficulty(role === "adjudicator" ? "" : active?.review?.difficulty || "");
    setReason(role === "adjudicator" ? active?.primary?.adjudication?.reason || "" : "");
  }, [active, role]);

  const save = async () => {
    if (!snapshot?.file_version || !active) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const rows = abstention.trim() ? [] : signals;
      await callAdvisor("evaluation", {action: "save", role, record_id: active.record_id,
        file_version: snapshot.file_version, reviewer_id: reviewer.trim(),
        signals: rows, abstention_reason: abstention.trim() || null,
        difficulty: difficulty.trim() || null, reason: reason.trim() || null}, event => {
        if (event.type === "evaluation") setSnapshot(event.evaluation);
      });
      setNotice("Review saved. The frozen source packet was not changed.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Review could not be saved."); }
    finally { setBusy(false); }
  };
  const changeSignal = (index: number, patch: Partial<Draft>) => setSignals(rows => rows.map((row, i) => i === index ? {...row, ...patch} : row));
  const visible = snapshot?.items?.filter(item => filter === "all" || item.split === filter) || [];
  const metric = (value: number | null | undefined) => value == null ? "Unmeasured" : `${(value * 100).toFixed(1)}%`;

  return <>
    <PageHeader title="Evaluation" question="Record independent human judgments on frozen customer evidence and measure extraction coverage." />
    {!snapshot?.available ? <section className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-600">
      {error ? <p role="alert" className="text-red-700">{error}</p> : <p>{snapshot?.message || "Checking the frozen evaluation set…"}</p>}
      <p className="mt-3">From the repository root, run <code className="rounded bg-slate-100 px-1">uv run bmw-pm freeze-evaluation</code> to create the private 120-record set.</p>
    </section> : <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[["Frozen cases", snapshot.total], ["Scoring ready", snapshot.counts?.gold_ready],
          ["Needs review", snapshot.counts?.unlabelled], ["Awaiting second review or resolution", snapshot.counts?.provisional],
          ["AI-assisted first reviews", snapshot.counts?.ai_assisted_first_reviews]].map(([title, value]) =>
          <div key={String(title)} className="rounded-md border border-slate-200 bg-white p-3"><p className="text-xs text-slate-500">{title}</p><p className="mt-1 text-xl font-semibold tabular-nums">{value}</p></div>)}
      </div>
      <section className="mt-4 rounded-md border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold">Baseline extraction</h2>
        <p className="mt-1 text-xs text-slate-500">Results are scored only against completed human labels. AI-assisted first reviews are counted separately. Exact topic, polarity and quote overlap are a proxy; detailed topics may differ from the baseline taxonomy. Citation entailment and decision quality still need separate review.</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">{splits.map(split => {
          const row = snapshot.baseline?.[split];
          return <div key={split} className="rounded border border-slate-100 bg-slate-50 p-3 text-xs">
            <p className="font-medium text-zinc-900">{splitLabels[split]}</p>
            <p className="mt-2">Scored: {row?.scored_records ?? 0} / {row?.records ?? 0}</p>
            <p>F1: <strong>{metric(row?.metrics?.f1)}</strong></p>
            <p>Precision: {metric(row?.metrics?.precision)} · Recall: {metric(row?.metrics?.recall)}</p>
            <p className="mt-1 text-slate-500">{row ? `${row.statuses.success || 0} extracted · ${row.statuses.abstained || 0} abstained · ${row.statuses.failed || 0} failed` : "Baseline run not available"}</p>
          </div>;
        })}</div>
      </section>
      <div className="mt-4 grid items-start gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <section className="rounded-md border border-slate-200 bg-white p-4">
          <label className={labelClass}>Review stage</label>
          <select className={fieldClass} value={role} onChange={event => {const next = event.target.value as Role; setRole(next); void load(next);}}>
            <option value="primary">First review</option><option value="secondary">Independent second review</option><option value="adjudicator">Resolve two reviews</option>
          </select>
          <p className="mt-2 text-xs text-slate-500">The second reviewer sees the frozen text without the first reviewer&apos;s labels. Use a different reviewer ID.</p>
          <label className={`${labelClass} mt-4`}>Packet split</label>
          <select className={fieldClass} value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All splits</option>{splits.map(split => <option key={split} value={split}>{splitLabels[split]}</option>)}</select>
          <div className="mt-3 max-h-96 space-y-1 overflow-y-auto">{visible.map(item => <button key={item.record_id} type="button"
            onClick={() => void load(role, item.record_id)} className={`block w-full rounded px-2 py-1.5 text-left text-xs ${active?.record_id === item.record_id ? "bg-brand-soft text-brand" : "hover:bg-slate-50"}`}>
            <span className="font-mono">{item.record_id}</span><span className="ml-2 text-slate-500">{item.model} · {item.status}{item.double_label ? " · double" : ""}</span>
          </button>)}</div>
        </section>
        {active && <section className="rounded-md border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-sm font-semibold">{active.record_id}</h2><span className="text-xs text-slate-500">{splitLabels[active.split]} · {active.country || "market unknown"} · {active.powertrain || "powertrain unknown"}</span></div>
          <p className="mt-2 text-xs text-slate-500">Private redacted feedback. Source label {active.source_label || "unknown"}; hash {active.content_hash.slice(0, 12)}. Do not infer buyer status or severity from this text.</p>
          {role === "primary" && active.review?.review_method === "ai_assisted_verified" && <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-900">This first review was verified from an AI draft. Its draft hash is retained; any edits remain marked AI-assisted.</p>}
          <div className="mt-3 whitespace-pre-wrap rounded border border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed" data-testid="frozen-text">{active.text}</div>
          {role === "adjudicator" && <div className="mt-4 grid gap-3 md:grid-cols-2">{[["First review", active.primary], ["Second review", active.secondary]].map(([title, label]) =>
            <div key={String(title)} className="rounded border border-slate-200 p-3 text-xs"><p className="font-semibold">{String(title)}</p><pre className="mt-2 whitespace-pre-wrap break-words font-sans text-slate-600">{label ? JSON.stringify(label, null, 2) : "No completed review"}</pre></div>)}</div>}
          <div className="mt-5 border-t border-slate-100 pt-4"><h3 className="text-sm font-semibold">{role === "adjudicator" ? "Resolved label" : "Your independent label"}</h3>
            <p className="mt-1 text-xs text-slate-500">Identify each atomic need separately. Copy an exact, uniquely occurring quote from the text above. If no supported need exists, explain the abstention.</p>
            <label className={`${labelClass} mt-3`}>Reviewer ID</label><input className={fieldClass} value={reviewer} onChange={event => setReviewer(event.target.value)} maxLength={100} />
            {signals.map((signal, index) => <div key={index} className="mt-3 rounded border border-slate-200 p-3">
              <div className="flex items-center justify-between"><p className="text-xs font-semibold">Signal {index + 1}</p>{signals.length > 1 && <button type="button" className="text-xs text-red-700" onClick={() => setSignals(rows => rows.filter((_, i) => i !== index))}>Remove</button>}</div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <label><span className={labelClass}>Topic</span><input className={fieldClass} list="evaluation-domains" value={signal.need_domain} onChange={event => changeSignal(index, {need_domain: event.target.value})} placeholder="Choose or enter a topic" /></label>
                <label><span className={labelClass}>Polarity</span><select className={fieldClass} value={signal.polarity} onChange={event => changeSignal(index, {polarity: event.target.value as Draft["polarity"]})}>{["complaint", "praise", "aspiration", "observation", "mixed"].map(value => <option key={value}>{value}</option>)}</select></label>
                <label className="sm:col-span-2"><span className={labelClass}>Atomic claim</span><input className={fieldClass} value={signal.atomic_claim} onChange={event => changeSignal(index, {atomic_claim: event.target.value})} placeholder="What this person actually establishes" /></label>
                <label className="sm:col-span-2"><span className={labelClass}>Customer outcome</span><input className={fieldClass} value={signal.customer_outcome} onChange={event => changeSignal(index, {customer_outcome: event.target.value})} placeholder="What should become easier or better" /></label>
                <label className="sm:col-span-2"><span className={labelClass}>Exact evidence quote</span><textarea className={fieldClass} rows={2} value={signal.evidence_text} onChange={event => changeSignal(index, {evidence_text: event.target.value})} /></label>
              </div>
            </div>)}
            <datalist id="evaluation-domains">{domains.map(domain => <option key={domain} value={domain} />)}</datalist>
            <Button type="button" className="mt-3" onClick={() => {setAbstention(""); setSignals(rows => [...rows, emptySignal()]);}}>Add another signal</Button>
            <label className={`${labelClass} mt-4`}>Abstention reason · leave signals empty when used</label><textarea className={fieldClass} rows={2} value={abstention} onChange={event => setAbstention(event.target.value)} placeholder="Why no atomic claim can be supported" />
            {role === "adjudicator" ? <><label className={`${labelClass} mt-3`}>Resolution reason</label><textarea className={fieldClass} rows={2} value={reason} onChange={event => setReason(event.target.value)} placeholder="How both reviews were reconciled" /></>
              : <><label className={`${labelClass} mt-3`}>Difficulty or ambiguity (optional)</label><input className={fieldClass} value={difficulty} onChange={event => setDifficulty(event.target.value)} /></>}
            {error && <p role="alert" className="mt-3 text-xs text-red-700">{error}</p>}{notice && <p role="status" className="mt-3 text-xs text-green-700">{notice}</p>}
            <div className="mt-4 flex gap-2"><Button type="button" variant="primary" disabled={busy} onClick={() => void save()}>{busy ? "Working…" : "Save human review"}</Button><Button type="button" disabled={busy} onClick={() => void load(role, active.record_id)}>Reload</Button></div>
          </div>
        </section>}
      </div>
      <p className="mt-4 text-xs text-slate-500">Frozen packets and labels are private local files under <code>runs/evaluation-v1</code>. Reviewer IDs identify entries, but this local screen does not authenticate people. Results are exploratory until sufficient independent reviews are complete.</p>
    </>}
  </>;
}
