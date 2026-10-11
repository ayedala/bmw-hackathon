"use client";
import {useState} from "react";
import {Download, ExternalLink, FileText} from "lucide-react";
import {Button} from "@/components/ui/button";
import {SidePanel} from "@/components/ui/dialog";
import {Tabs, TabsContent, TabsList, TabsTrigger} from "@/components/ui/tabs";
import type {AdvisorResult, Claim, EvidenceItem} from "@/lib/advisor/contracts";
import {VEHICLES} from "@/lib/advisor/contracts";
import {StudioEconomics} from "./studio-economics";

function safeLink(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null; } catch { return null; }
}
const labels = {evidence: "Sourced claim · review pending", inference: "Agent assessment", assumption: "Assumption to test", unknown: "Evidence gap"};
function ClaimView({claim, sources, inspect}: {claim: Claim; sources: Map<string, EvidenceItem>; inspect: (item: EvidenceItem) => void}) {
  return <div className="space-y-1.5 py-2"><p className="text-2xs font-medium uppercase tracking-wide text-slate-500">{labels[claim.basis]}</p>
    <p className="text-[13px] leading-relaxed">{claim.text}</p>{claim.explanation && <p className="text-xs leading-relaxed text-slate-500">{claim.explanation}</p>}
    <div className="flex flex-wrap gap-1.5">{Array.from(new Set(claim.evidence_ids)).map(id => {const item = sources.get(id); return item ? <button key={id} type="button" onClick={() => inspect(item)} className="rounded-sm border border-brand-line bg-brand-soft px-1.5 py-0.5 text-2xs text-brand" title={item.title}>{id}</button> : null;})}</div>
  </div>;
}
function List({items}: {items: string[]}) {return <ul className="list-disc space-y-1.5 pl-4 text-xs leading-relaxed text-slate-600">{items.map((item, i) => <li key={i}>{item}</li>)}</ul>;}

export function AdvisorReport({result}: {result: AdvisorResult}) {
  const [selected, setSelected] = useState<EvidenceItem | null>(null);
  const [filter, setFilter] = useState("all");
  const request = result.packet.request;
  const sources = new Map([...result.packet.evidence, ...result.research.sources].map(item => [item.evidence_id, item]));
  const preferred = result.report.options.find(option => option.option_id === result.report.preferred_option_id);
  const claim = (value: Claim) => <ClaimView claim={value} sources={sources} inspect={setSelected} />;
  const original = selected && safeLink(selected.locator.url);
  const evidence = [...result.packet.evidence, ...result.research.sources];
  const exportBrief = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: "application/json"}));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `bmw-${request.model_code}-${result.run_id}.json`; anchor.click(); URL.revokeObjectURL(url);
  };
  return <section className="min-w-0 rounded-md border border-slate-200 bg-white p-4 sm:p-5" aria-label="Decision brief">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-2xs font-medium uppercase tracking-wide text-brand">Live research · provisional decision</p><h2 className="mt-1 text-lg font-semibold tracking-tight">{result.report.headline}</h2><p className="mt-1 text-xs text-slate-500">{VEHICLES[request.model_code]} · {request.model_code} / {request.market} / {request.powertrain} · {new Date(result.created_at).toLocaleString()}</p></div><Button size="sm" onClick={exportBrief}><Download />Download brief</Button></div>
    <p className="mt-4 text-[13px] leading-relaxed text-slate-600">{result.report.summary}</p>
    <div className="my-4 border-l-2 border-brand bg-brand-soft px-3 py-2 text-xs"><span className="font-semibold">{preferred ? "Provisional preference: " : "No preferred option established. "}</span>{preferred?.title || "The available evidence does not separate the options yet."}</div>
    <Tabs defaultValue="decision">
      <TabsList className="gap-3 overflow-x-auto">{[["decision", "Decision"], ["evidence", "Evidence"], ["market", "Market research"], ["economics", "Costs & revenue"], ["process", "Process"]].map(([id, label]) => <TabsTrigger key={id} value={id!} className="whitespace-nowrap text-xs">{label}</TabsTrigger>)}</TabsList>
      <TabsContent value="decision" className="space-y-4">
        {claim(result.report.recommendation)}
        {result.report.options.map((option, index) => <article key={option.option_id} className="rounded-md border border-slate-200 p-4">
          <h3 className="text-sm font-semibold">{option.title}</h3><p className="mt-1 text-xs leading-relaxed text-slate-600">{option.proposal}</p>
          {request.journey === "compare" && <p className="mt-2 text-2xs text-slate-500">Submitted idea {index + 1}: {request.ideas[index]}</p>}
          <h4 className="mt-4 text-xs font-semibold">Customer value</h4>{option.customer_case.map((item, i) => <div key={i}>{claim(item)}</div>)}
          <details className="mt-3 border-t border-slate-100 pt-3"><summary className="cursor-pointer text-xs font-semibold">Can it be built and shipped?</summary>{claim(option.feasibility)}<h5 className="my-2 text-xs font-medium">Proposed delivery path</h5><List items={option.delivery_steps} /><h5 className="my-2 text-xs font-medium">Risks and validation gates</h5><List items={[...option.risks, ...option.validation_needed]} /></details>
          <details className="mt-3 border-t border-slate-100 pt-3"><summary className="cursor-pointer text-xs font-semibold">Competitor implementations</summary>{option.competitors.map((item, i) => <div key={i}>{claim(item)}</div>)}</details>
          <details className="mt-3 border-t border-slate-100 pt-3"><summary className="cursor-pointer text-xs font-semibold">Cost and revenue outlook</summary>{claim(option.cost_outlook)}{claim(option.revenue_outlook)}</details>
        </article>)}
        <h3 className="text-sm font-semibold">Why this option, and what could change the decision</h3>{result.report.comparison.map((item, i) => <div key={i}>{claim(item)}</div>)}
        {result.report.follow_up_questions.length > 0 && <div className="rounded-md bg-slate-50 p-4"><h3 className="mb-2 text-xs font-semibold">Answers that would improve the assessment</h3><List items={result.report.follow_up_questions} /><p className="mt-3 text-2xs text-slate-500">Add your answers in the constraints field, then run another assessment.</p></div>}
      </TabsContent>
      <TabsContent value="evidence" className="space-y-4">
        <p className="text-xs text-slate-600"><strong>{result.packet.feedback_records.toLocaleString()} scoped feedback records.</strong> Unique IDs, not verified people. Video evidence remains a separate source.</p>
        <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="border-b border-slate-200 text-slate-500"><tr>{["Topic", "Support", "Praise", "Mixed", "Applicable"].map(text => <th key={text} className="py-2 pr-3 font-medium">{text}</th>)}</tr></thead><tbody>{result.packet.topics.map(topic => <tr key={topic.domain} className="border-b border-slate-100"><td className="py-2 pr-3">{topic.domain.replaceAll("_", " ")}</td><td>{topic.supporting_records}</td><td>{topic.praise_records}</td><td>{topic.context_records}</td><td>{topic.eligible_records}</td></tr>)}</tbody></table></div>
        <p className="text-2xs text-slate-500">Topic counts use the existing keyword baseline and do not predict sales impact.</p>
        <label className="flex items-center gap-2 text-xs">Source type<select className="rounded-md border border-slate-200 px-2 py-1" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All selected evidence</option>{Array.from(new Set(evidence.map(item => item.channel))).map(channel => <option key={channel} value={channel}>{channel.replaceAll("_", " ")}</option>)}</select></label>
        <div className="space-y-2">{evidence.filter(item => filter === "all" || item.channel === filter).map(item => <button key={item.evidence_id} type="button" onClick={() => setSelected(item)} className="block w-full rounded-md border border-slate-200 p-3 text-left hover:border-brand-line"><span className="flex items-center gap-2 text-xs font-semibold"><FileText className="size-3.5 shrink-0 text-slate-400" />{item.title}</span><span className="mt-1 block text-2xs text-slate-500">{item.channel.replaceAll("_", " ")} · {item.evidence_id}</span><span className="mt-2 block text-xs leading-relaxed text-slate-600">{item.selection_reason}</span></button>)}</div>
      </TabsContent>
      <TabsContent value="market" className="space-y-4"><p className="whitespace-pre-wrap text-[13px] leading-relaxed">{result.research.text.split(/(\[web:\d+\])/).map((part, i) => {const item = sources.get(part.slice(1, -1)); const url = item && safeLink(item.locator.url); return url ? <a key={i} className="text-brand underline" href={url} target="_blank" rel="noopener noreferrer">{part}</a> : part;})}</p>
        {result.research.sources.map(item => <div key={item.evidence_id} className="border-t border-slate-100 py-3"><button onClick={() => setSelected(item)} className="text-left text-xs font-medium text-brand">{item.title} · {item.evidence_id}</button></div>)}
      </TabsContent>
      <TabsContent value="economics" forceMount className="space-y-4 data-[state=inactive]:hidden">{result.report.options.map(option => <div key={option.option_id}><h3 className="text-sm font-semibold">{option.title}</h3>{claim(option.cost_outlook)}{claim(option.revenue_outlook)}</div>)}<StudioEconomics key={result.run_id} result={result} /></TabsContent>
      <TabsContent value="process" className="space-y-4"><div><h3 className="mb-2 text-xs font-semibold">Completed steps</h3><List items={result.steps} /></div><div><h3 className="mb-2 text-xs font-semibold">Why these sources?</h3><p className="text-xs leading-relaxed text-slate-600">{result.plan.rationale}</p></div><List items={result.plan.research_questions} /><div><h3 className="mb-2 text-xs font-semibold">Limits affecting the decision</h3><List items={result.packet.limitations} /></div><p className="break-all font-mono text-2xs text-slate-400">Run: {result.run_id}<br />Evidence snapshot: {result.packet.fingerprint}</p></TabsContent>
    </Tabs>
    <SidePanel open={Boolean(selected)} onOpenChange={open => {if (!open) setSelected(null);}} title={selected?.title || "Source"} eyebrow={selected?.channel.replaceAll("_", " ")}
      footer={original ? <Button asChild><a href={original} target="_blank" rel="noopener noreferrer"><ExternalLink />Open original source</a></Button> : undefined}>
      {selected && <div className="space-y-4"><p className="whitespace-pre-wrap text-[13px] leading-relaxed">{selected.text}</p><div><h3 className="mb-1 text-xs font-semibold">Why selected</h3><p className="text-xs leading-relaxed text-slate-600">{selected.selection_reason}</p></div><List items={selected.limitations} /><details><summary className="cursor-pointer text-xs font-medium">Scope and original locator</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-2xs text-slate-500">{JSON.stringify({scope: selected.scope, locator: selected.locator}, null, 2)}</pre></details></div>}
    </SidePanel>
  </section>;
}
