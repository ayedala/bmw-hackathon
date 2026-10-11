"use client";
import {useState, type FormEvent} from "react";
import Link from "next/link";
import {ArrowRight, BookOpen, CheckCircle2, Lightbulb, LoaderCircle, Scale, Search, Square, WandSparkles} from "lucide-react";
import {PageHeader} from "@/components/app/layout-parts";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {useStudio} from "@/lib/advisor/store";
import {MARKETS, VEHICLES, type Journey, type Vehicle} from "@/lib/advisor/contracts";
import {cn} from "@/lib/utils";
import {AdvisorReport} from "./studio-report";

export const fieldClass = "w-full rounded-md border border-slate-200 bg-white px-2.5 py-2 text-[13px] text-ink focus:outline-none focus:ring-2 focus:ring-brand/30 disabled:bg-slate-50";
export const labelClass = "mb-1.5 block text-xs font-medium text-zinc-800";
const journeys = [
  {id: "idea", label: "Assess my idea", detail: "Test demand, feasibility and economics", icon: Lightbulb},
  {id: "improve", label: "Find an improvement", detail: "Find the next opportunity for a BMW", icon: WandSparkles},
  {id: "compare", label: "Compare ideas", detail: "Assess 2–5 options on the same basis", icon: Scale},
] as const;

export function DecisionStudioScreen() {
  const studio = useStudio();
  const {request, setRequest, catalog, result, running, steps, error} = studio;
  const [advanced, setAdvanced] = useState(false);
  const records = catalog?.scopes.filter(row => row.model_code === request.model_code && row.market === request.market &&
    (request.powertrain === "ALL" || row.powertrain === request.powertrain)).reduce((total, row) => total + row.feedback_records, 0);
  const submit = (event: FormEvent) => {event.preventDefault(); void studio.run();};
  return <>
    <PageHeader title="What should we build next?" question="Turn customer evidence, video research and market context into a reviewable product decision."
      actions={<Button asChild><Link href="/video-memory"><BookOpen />Video memory</Link></Button>} />
    <div className="grid items-start gap-5 xl:grid-cols-[370px_minmax(0,1fr)]">
      <form onSubmit={submit} className="space-y-4 rounded-md border border-slate-200 bg-white p-4">
        <fieldset disabled={running} className="space-y-4">
          <legend className="mb-3 text-[13px] font-semibold">What would you like to decide?</legend>
          <div role="radiogroup" aria-label="Decision type" className="space-y-2">
            {journeys.map(({id, label, detail, icon: Icon}) => <button key={id} type="button" role="radio" aria-checked={request.journey === id}
              onClick={() => setRequest({...request, journey: id as Journey})}
              className={cn("flex w-full items-center gap-3 rounded-md border px-3 py-2.5 text-left", request.journey === id ? "border-brand-line bg-brand-soft" : "border-slate-200 hover:bg-slate-50")}>
              <Icon className={cn("size-4 shrink-0", request.journey === id ? "text-brand" : "text-slate-400")} />
              <span><span className="block text-xs font-semibold">{label}</span><span className="text-2xs text-slate-500">{detail}</span></span>
            </button>)}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label><span className={labelClass}>BMW model</span><select className={fieldClass} value={request.model_code} onChange={e => {
              const model_code = e.target.value as Vehicle;
              setRequest({...request, model_code, powertrain: model_code === "F70" ? "ICE" : "ALL", market: model_code === "F70" ? "GB" : "US"});
            }}>{Object.entries(VEHICLES).map(([value, label]) => <option key={value} value={value}>{label} · {value}</option>)}</select></label>
            <label><span className={labelClass}>Target market</span><select className={fieldClass} value={request.market} onChange={e => setRequest({...request, market: e.target.value})}>
              {Object.entries(MARKETS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
          </div>
          <label className="block"><span className={labelClass}>Powertrain</span><select className={fieldClass} value={request.powertrain}
            onChange={e => setRequest({...request, powertrain: e.target.value as typeof request.powertrain})}>
            {(request.model_code === "F70" ? ["ICE"] : ["ALL", "ICE", "PHEV", "BEV"]).map(value => <option key={value}>{value}</option>)}
          </select></label>
          {request.journey === "compare" ? <label className="block"><span className={labelClass}>Ideas to compare · one per line</span>
            <textarea className={fieldClass} rows={5} required maxLength={5000} value={studio.ideaText} onChange={e => studio.setIdeaText(e.target.value)}
              placeholder={"Add tactile climate shortcuts\nImprove voice control accuracy"} /></label>
            : <label className="block"><span className={labelClass}>{request.journey === "idea" ? "Describe your idea" : "Any area to focus on? (optional)"}</span>
              <textarea className={fieldClass} rows={4} required={request.journey === "idea"} minLength={request.journey === "idea" ? 10 : undefined} maxLength={4000}
                value={request.question} onChange={e => setRequest({...request, question: e.target.value})}
                placeholder={request.journey === "idea" ? "For example: improve exterior styling and wheel design while preserving ride comfort." : "Leave open to compare needs, or focus on design, comfort, software…"} /></label>}
          <label className="block"><span className={labelClass}>What matters most?</span><select className={fieldClass} value={request.objective} onChange={e => setRequest({...request, objective: e.target.value})}>
            {["Balanced customer value and business potential", "Customer satisfaction and retention", "Revenue and profitable growth", "Competitive differentiation"].map(value => <option key={value}>{value}</option>)}
          </select></label>
          <label className="block"><span className={labelClass}>Constraints or follow-up answers</span><textarea className={fieldClass} rows={2} maxLength={800}
            value={studio.constraints} onChange={e => studio.setConstraints(e.target.value)} placeholder="Budget, timing, features to preserve…" /></label>
          <button type="button" onClick={() => setAdvanced(!advanced)} aria-expanded={advanced} className="text-xs font-medium text-brand">{advanced ? "Hide" : "Show"} planning assumptions</button>
          {advanced && <div className="grid grid-cols-2 gap-3 border-t border-slate-100 pt-3">
            <label><span className={labelClass}>Model year</span><Input type="number" min={2020} max={2040} required value={request.model_year} onChange={e => setRequest({...request, model_year: Number(e.target.value)})} /></label>
            <label><span className={labelClass}>Planning years</span><Input type="number" min={1} max={10} required value={request.planning_years} onChange={e => setRequest({...request, planning_years: Number(e.target.value)})} /></label>
            <label><span className={labelClass}>Currency</span><select className={fieldClass} value={request.currency} onChange={e => setRequest({...request, currency: e.target.value})}>{["EUR", "USD", "GBP"].map(c => <option key={c}>{c}</option>)}</select></label>
            <label><span className={labelClass}>Budget cap (optional)</span><Input type="number" min={1} value={request.budget ?? ""} onChange={e => setRequest({...request, budget: e.target.value ? Number(e.target.value) : null})} /></label>
          </div>}
        </fieldset>
        <div className="rounded-md bg-slate-50 p-3 text-xs text-slate-600">
          {records !== undefined ? <><strong className="font-medium text-zinc-900">{records.toLocaleString()} scoped feedback records</strong><p className="mt-1">{records ? "Unique feedback IDs; not a representative customer sample." : "No matching feedback. Research will show this gap."}</p></> : "Checking the evidence database…"}
          {catalog && <><p className="mt-2">{catalog.database_backend === "postgres" ? "Connected to the shared team dataset." : "Connected to the local dataset."}</p><p className="mt-2">Video library across models: {catalog.youtube_findings} validated findings · {catalog.video_memories} saved transcripts.</p></>}
        </div>
        {studio.catalogError && <p role="alert" className="text-xs text-red-700">{studio.catalogError}</p>}
        {catalog && !catalog.connection_configured && <p className="text-xs text-amber-800">Add your API key to the repository’s <code>.env.local</code> file. <button type="button" className="underline" onClick={() => void studio.refreshCatalog()}>Check again</button></p>}
        {catalog && !catalog.database_available && <p className="text-xs text-red-700">The evidence database needs to be imported before research can start.</p>}
        <p className="text-2xs leading-relaxed text-slate-500">Research sends selected redacted excerpts to OpenAI and public questions to web search. API usage charges apply.</p>
        {running ? <Button type="button" onClick={studio.stop} className="w-full"><Square />Stop research</Button>
          : <Button type="submit" variant="primary" className="w-full" disabled={catalog?.database_available === false}><Search />Research and assess<ArrowRight /></Button>}
      </form>
      <div className="min-w-0 space-y-4">
        {(running || steps.length > 0 || error) && <section className="rounded-md border border-slate-200 bg-white p-4" aria-label="Research progress" aria-live="polite">
          <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold">{running ? <LoaderCircle className="size-4 animate-spin text-brand" /> : result ? <CheckCircle2 className="size-4 text-brand" /> : null}
            {running ? "Building your decision brief" : error ? "Research stopped" : "Decision brief ready"}</div>
          <ol className="space-y-2 text-xs text-slate-600">{steps.map((step, i) => <li key={i} className="flex gap-2"><span className="font-mono text-slate-400">{String(i + 1).padStart(2, "0")}</span>{step}</li>)}</ol>
          {error && <p role="alert" className="mt-3 rounded-md bg-red-50 p-3 text-xs text-red-800">{error}</p>}
        </section>}
        {result ? <AdvisorReport result={result} /> : !running && !error && <section className="rounded-md border border-slate-200 bg-white px-6 py-12">
          <div className="mb-5 inline-flex rounded-md bg-brand-soft p-3 text-brand"><Lightbulb className="size-6" /></div>
          <h2 className="text-lg font-semibold tracking-tight">A decision starts with evidence.</h2>
          <p className="mt-2 max-w-lg text-[13px] leading-relaxed text-slate-500">Choose a path on the left. Your brief will connect customer needs to concrete options, explain why evidence was selected, and show what still needs to be validated.</p>
          <div className="mt-8 grid gap-5 sm:grid-cols-3">{[["01", "Understand", "Read scoped customer feedback and reusable video transcripts."], ["02", "Investigate", "Research competitors, implementation paths and current market evidence."], ["03", "Compare", "Weigh customer value, feasibility, risks and conditional economics."]].map(([number, title, description]) => <div key={number} className="border-t border-slate-200 pt-3"><p className="font-mono text-2xs text-brand">{number}</p><h3 className="mt-1 text-xs font-semibold">{title}</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">{description}</p></div>)}</div>
        </section>}
      </div>
    </div>
  </>;
}
