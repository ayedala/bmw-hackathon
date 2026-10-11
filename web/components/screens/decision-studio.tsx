"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import {
  ArrowRight, BookOpen, Check, CheckCircle2, ChevronDown, CircleHelp, Database,
  Lightbulb, LoaderCircle, Search, SlidersHorizontal, Sparkles, Square, Waypoints,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MARKETS, VEHICLES, type Journey, type Vehicle } from "@/lib/advisor/contracts";
import { useStudio } from "@/lib/advisor/store";
import { cn } from "@/lib/utils";
import { AdvisorReport } from "./studio-report";

export const fieldClass = "w-full rounded-md border border-slate-200 bg-white px-3 py-2.5 text-[13px] text-ink shadow-sm outline-none transition-colors placeholder:text-slate-400 focus:border-brand focus:ring-2 focus:ring-brand/15 disabled:bg-slate-50";
export const labelClass = "mb-1.5 block text-xs font-semibold text-zinc-800";

const journeys = [
  { id: "idea", number: "01", label: "Explore an idea", detail: "Can we build it, and is it worth it?", icon: Lightbulb },
  { id: "improve", number: "02", label: "Find an opportunity", detail: "Let the evidence suggest the next move.", icon: Sparkles },
  { id: "compare", number: "03", label: "Compare ideas", detail: "Put several options on the same basis.", icon: Waypoints },
] as const;

const objectives = [
  { value: "Balanced customer value and business potential", label: "Balanced", detail: "Customer + business" },
  { value: "Customer satisfaction and retention", label: "Customer", detail: "Satisfaction + loyalty" },
  { value: "Revenue and profitable growth", label: "Growth", detail: "Revenue + margin" },
  { value: "Competitive differentiation", label: "Differentiate", detail: "Stand out in market" },
];

const prompts: Record<Journey, { label: string; text: string }[]> = {
  idea: [
    { label: "Exterior design", text: "Improve the exterior styling and wheel design while preserving ride comfort." },
    { label: "Cabin controls", text: "Add tactile climate controls that reduce distraction without losing the clean cabin design." },
    { label: "Charging", text: "Make long-distance charging easier to plan and more reliable for drivers." },
  ],
  improve: [
    { label: "Design", text: "Focus on exterior design and personalization." },
    { label: "Comfort", text: "Focus on ride comfort and cabin noise." },
    { label: "Software", text: "Focus on software reliability and in-car controls." },
  ],
  compare: [
    { label: "Cabin experience", text: "Add tactile climate shortcuts\nImprove voice control accuracy\nSimplify the main touchscreen menus" },
    { label: "Driving experience", text: "Improve ride comfort on rough roads\nReduce cabin noise at highway speeds\nImprove driver-assistance handoff clarity" },
  ],
};

function DecisionPath({ journey, onChange }: { journey: Journey; onChange: (value: Journey) => void }) {
  return <div role="radiogroup" aria-label="Decision path" className="grid gap-2 sm:grid-cols-3">
    {journeys.map(({ id, number, label, detail, icon: Icon }) => {
      const active = journey === id;
      return <button key={id} type="button" role="radio" aria-checked={active} onClick={() => onChange(id)}
        className={cn("group relative min-h-28 rounded-md border p-3 text-left transition-all duration-150 hover:-translate-y-0.5 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35",
          active ? "border-brand bg-brand-soft shadow-[0_0_0_1px_#0066cc]" : "border-slate-200 bg-white hover:border-slate-300")}>
        <div className="mb-2 flex items-center justify-between">
          <span className={cn("inline-flex size-8 items-center justify-center rounded-md", active ? "bg-brand text-white" : "bg-slate-100 text-slate-600")}><Icon className="size-4" aria-hidden /></span>
          <span className="font-mono text-2xs text-slate-400">{number}</span>
        </div>
        <span className="block text-xs font-semibold text-zinc-950">{label}</span>
        <span className="mt-1 block text-2xs leading-4 text-slate-600">{detail}</span>
        {active && <Check className="absolute right-3 top-3 size-3.5 text-brand" aria-hidden />}
      </button>;
    })}
  </div>;
}

function StudioWelcome() {
  return <section className="relative overflow-hidden rounded-md border border-slate-200 bg-white p-6 sm:p-8" aria-label="How the decision studio works">
    <div aria-hidden className="pointer-events-none absolute -right-20 -top-20 size-72 rounded-full border-[48px] border-brand-soft" />
    <div aria-hidden className="pointer-events-none absolute -bottom-20 right-20 size-52 rounded-full border-[28px] border-slate-50" />
    <div className="relative max-w-lg">
      <span className="inline-flex items-center gap-2 rounded-full border border-brand-line bg-brand-soft px-2.5 py-1 text-2xs font-semibold text-brand"><Waypoints className="size-3.5" /> YOUR DECISION PATH</span>
      <h2 className="mt-5 text-2xl font-semibold tracking-tight text-zinc-950">From a question to a decision you can inspect.</h2>
      <p className="mt-3 text-[13px] leading-6 text-slate-600">Choose how you want to start. The studio will connect customer feedback, market research and business assumptions, then show the source and limits behind each suggestion.</p>
    </div>
    <ol className="relative mt-8 grid gap-3 sm:grid-cols-3">
      {[
        ["01", "Scope", "Choose the car and market."],
        ["02", "Research", "Follow the evidence trail."],
        ["03", "Decide", "Compare options and gaps."],
      ].map(([number, title, detail]) => <li key={number} className="rounded-md border border-slate-200 bg-white/90 p-3">
        <span className="font-mono text-2xs font-semibold text-brand">{number}</span>
        <h3 className="mt-1 text-xs font-semibold text-zinc-900">{title}</h3>
        <p className="mt-1 text-2xs leading-4 text-slate-600">{detail}</p>
      </li>)}
    </ol>
  </section>;
}

export function DecisionStudioScreen() {
  const studio = useStudio();
  const { request, setRequest, catalog, result, running, steps, error } = studio;
  const [advanced, setAdvanced] = useState(false);
  const [constraintsOpen, setConstraintsOpen] = useState(false);
  const ideas = studio.ideaText.split("\n").map((line) => line.trim()).filter(Boolean);
  const uniqueIdeas = new Set(ideas.map((line) => line.toLocaleLowerCase())).size;
  const validInput = request.journey === "compare" ? ideas.length >= 2 && ideas.length <= 5 && uniqueIdeas === ideas.length
    : request.journey === "idea" ? request.question.trim().length >= 10 : true;
  const scoped = catalog?.scopes.filter((row) => row.model_code === request.model_code && row.market === request.market &&
    (request.powertrain === "ALL" || row.powertrain === request.powertrain)) ?? [];
  const records = scoped.reduce((total, row) => total + row.feedback_records, 0);
  const submit = (event: FormEvent) => { event.preventDefault(); if (validInput) void studio.run(); };
  const updateJourney = (journey: Journey) => {
    if (journey !== request.journey) setRequest({ ...request, journey, question: "" });
  };
  const startOver = () => { studio.reset(); studio.setIdeaText(""); studio.setConstraints(""); setRequest({ ...request, question: "" }); window.scrollTo({ top: 0, behavior: "smooth" }); };

  return <div className="mx-auto max-w-[1500px] space-y-5">
    <header className="relative overflow-hidden rounded-md bg-zinc-950 px-5 py-6 text-white sm:px-7 sm:py-7">
      <div aria-hidden className="absolute -right-14 -top-36 size-80 rounded-full border-[1px] border-white/15 shadow-[0_0_0_45px_rgba(255,255,255,.025),0_0_0_90px_rgba(255,255,255,.025)]" />
      <div className="relative flex flex-wrap items-end justify-between gap-4">
        <div><p className="mb-2 text-2xs font-semibold uppercase tracking-[0.2em] text-blue-300">BMW Product Decision Lab / Studio</p>
          <h1 className="max-w-2xl text-2xl font-semibold tracking-tight sm:text-3xl">What should we build next?</h1>
          <p className="mt-2 max-w-xl text-[13px] leading-5 text-slate-300">A clearer path from customer signals to a product recommendation.</p></div>
        <Button asChild variant="secondary" className="border-white/25 bg-white/10 text-white hover:bg-white/20"><Link href="/video-memory"><BookOpen />Video memory<ArrowRight /></Link></Button>
      </div>
    </header>

    <div className="grid items-start gap-5 xl:grid-cols-[minmax(390px,500px)_minmax(0,1fr)]">
      <form onSubmit={submit} className="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
        <fieldset disabled={running} className="space-y-6 p-4 sm:p-5">
          <div><div className="mb-3 flex items-center justify-between"><div><p className="font-mono text-2xs font-semibold text-brand">01 / START</p><h2 className="mt-1 text-base font-semibold tracking-tight text-zinc-950">Choose your path</h2></div><CircleHelp className="size-4 text-slate-400" aria-hidden /></div>
            <DecisionPath journey={request.journey} onChange={updateJourney} /></div>

          <div className="border-t border-slate-100 pt-5"><p className="font-mono text-2xs font-semibold text-brand">02 / FOCUS</p><h2 className="mt-1 text-base font-semibold tracking-tight text-zinc-950">Set the context</h2>
            <div className="mt-3 grid grid-cols-3 gap-2" role="radiogroup" aria-label="BMW model">
              {(Object.entries(VEHICLES) as [Vehicle, string][]).map(([code, name]) => <button key={code} type="button" role="radio" aria-checked={request.model_code === code}
                onClick={() => setRequest({ ...request, model_code: code, powertrain: code === "F70" ? "ICE" : "ALL", market: code === "F70" ? "GB" : "US" })}
                className={cn("rounded-md border px-2 py-3 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35",
                  request.model_code === code ? "border-brand bg-brand-soft shadow-[inset_0_-2px_0_#0066cc]" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50")}>
                <span className="block text-xs font-semibold text-zinc-950">{name}</span><span className="mt-0.5 block font-mono text-2xs text-slate-500">{code}</span>
              </button>)}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <label><span className={labelClass}>Target market</span><select className={fieldClass} value={request.market} onChange={(event) => setRequest({ ...request, market: event.target.value })}>{Object.entries(MARKETS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label><span className={labelClass}>Powertrain</span><select className={fieldClass} value={request.powertrain} onChange={(event) => setRequest({ ...request, powertrain: event.target.value as typeof request.powertrain })}>{(request.model_code === "F70" ? ["ICE"] : ["ALL", "ICE", "PHEV", "BEV"]).map((value) => <option key={value} value={value}>{value === "ALL" ? "All powertrains" : value}</option>)}</select></label>
            </div>
          </div>

          <div className="border-t border-slate-100 pt-5"><p className="font-mono text-2xs font-semibold text-brand">03 / YOUR QUESTION</p>
            <label className="mt-1 block"><span className="text-base font-semibold tracking-tight text-zinc-950">{request.journey === "idea" ? "Describe the idea" : request.journey === "compare" ? "Which ideas should we compare?" : "Where should we look?"}</span>
              <span className="mt-1 block text-xs leading-5 text-slate-600">{request.journey === "compare" ? "Add two to five distinct ideas, one per line." : request.journey === "improve" ? "Leave this open for a broad search, or choose a focus." : "Describe the customer change you want to make."}</span>
              {request.journey === "compare" ? <textarea className={cn(fieldClass, "mt-3 min-h-32 resize-y")} rows={5} maxLength={5000} value={studio.ideaText} onChange={(event) => studio.setIdeaText(event.target.value)} placeholder="One idea per line" />
                : <textarea className={cn(fieldClass, "mt-3 min-h-28 resize-y")} rows={4} maxLength={4000} value={request.question} onChange={(event) => setRequest({ ...request, question: event.target.value })} placeholder={request.journey === "idea" ? "What would change for the driver?" : "Optional area to explore"} />}
            </label>
            {request.journey === "compare" && <p role="status" className={cn("mt-1 text-2xs", ideas.length > 5 || (ideas.length > 1 && uniqueIdeas !== ideas.length) ? "text-amber-700" : "text-slate-500")}>{ideas.length} of 2–5 ideas {uniqueIdeas !== ideas.length ? "· remove duplicates" : ""}</p>}
            <div className="mt-3 flex flex-wrap items-center gap-1.5"><span className="mr-1 text-2xs text-slate-500">Try an example</span>{prompts[request.journey].map((prompt) => <button key={prompt.label} type="button" onClick={() => request.journey === "compare" ? studio.setIdeaText(prompt.text) : setRequest({ ...request, question: prompt.text })}
              className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-2xs font-medium text-slate-700 transition-colors hover:border-brand-line hover:bg-brand-soft hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35">{prompt.label}</button>)}</div>
          </div>

          <div className="border-t border-slate-100 pt-5"><p className="font-mono text-2xs font-semibold text-brand">04 / PRIORITY</p><h2 className="mt-1 text-base font-semibold tracking-tight text-zinc-950">What matters most?</h2>
            <div role="radiogroup" aria-label="Decision objective" className="mt-3 grid grid-cols-2 gap-2">{objectives.map(({ value, label, detail }) => <button key={value} type="button" role="radio" aria-checked={request.objective === value} onClick={() => setRequest({ ...request, objective: value })}
              className={cn("rounded-md border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35", request.objective === value ? "border-brand bg-brand-soft" : "border-slate-200 hover:bg-slate-50")}>
              <span className="block text-xs font-semibold text-zinc-900">{label}</span><span className="mt-0.5 block text-2xs text-slate-600">{detail}</span></button>)}</div>
          </div>

          <div className="border-t border-slate-100 pt-4"><button type="button" onClick={() => setConstraintsOpen(!constraintsOpen)} aria-expanded={constraintsOpen} className="flex w-full items-center justify-between text-left text-xs font-semibold text-zinc-800"><span className="inline-flex items-center gap-2"><SlidersHorizontal className="size-4 text-slate-500" />Constraints and planning assumptions</span><ChevronDown className={cn("size-4 text-slate-500 transition-transform", constraintsOpen && "rotate-180")} /></button>
            {constraintsOpen && <div className="mt-4 space-y-3"><label className="block"><span className={labelClass}>Constraints or follow-up answers</span><textarea className={fieldClass} rows={2} maxLength={800} value={studio.constraints} onChange={(event) => studio.setConstraints(event.target.value)} placeholder="Budget, timing, features to preserve…" /></label>
              <button type="button" onClick={() => setAdvanced(!advanced)} aria-expanded={advanced} className="text-xs font-medium text-brand hover:underline">{advanced ? "Hide" : "Show"} numeric assumptions</button>
              {advanced && <div className="grid grid-cols-2 gap-3 rounded-md bg-slate-50 p-3">
                <label><span className={labelClass}>Model year</span><Input type="number" min={2020} max={2040} required value={request.model_year} onChange={(event) => setRequest({ ...request, model_year: Number(event.target.value) })} /></label>
                <label><span className={labelClass}>Planning years</span><Input type="number" min={1} max={10} required value={request.planning_years} onChange={(event) => setRequest({ ...request, planning_years: Number(event.target.value) })} /></label>
                <label><span className={labelClass}>Currency</span><select className={fieldClass} value={request.currency} onChange={(event) => setRequest({ ...request, currency: event.target.value })}>{["EUR", "USD", "GBP"].map((currency) => <option key={currency}>{currency}</option>)}</select></label>
                <label><span className={labelClass}>Budget cap</span><Input type="number" min={1} value={request.budget ?? ""} onChange={(event) => setRequest({ ...request, budget: event.target.value ? Number(event.target.value) : null })} placeholder="Optional" /></label>
              </div>}
            </div>}
          </div>
        </fieldset>

        <div className="border-t border-slate-200 bg-slate-50 px-4 py-4 sm:px-5">
          <div className="mb-3 flex items-start gap-2.5"><span className={cn("mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-md", catalog?.database_available ? "bg-emerald-50 text-emerald-700" : "bg-slate-200 text-slate-600")}><Database className="size-4" /></span><div className="min-w-0"><p className="text-xs font-semibold text-zinc-900">{catalog ? `${records.toLocaleString()} scoped feedback records` : studio.catalogError ? "Evidence connection unavailable" : "Checking evidence coverage…"}</p><p className="text-2xs leading-4 text-slate-600">{catalog ? `${catalog.database_backend === "postgres" ? "Shared" : "Local"} dataset · ${records ? "unique record IDs, not a representative sample" : "no matching feedback in this scope"}` : studio.catalogError ? "Check the database connection, then retry." : "Connecting to the evidence database"}</p></div></div>
          {studio.catalogError && <div role="alert" className="mb-3 rounded-md border border-red-100 bg-red-50 p-2.5 text-xs text-red-700">{studio.catalogError} <button type="button" className="font-semibold underline" onClick={() => void studio.refreshCatalog()}>Retry connection</button></div>}
          {catalog && !catalog.connection_configured && <p className="mb-3 text-xs text-amber-800">Add an API key to <code>.env.local</code>. <button type="button" className="underline" onClick={() => void studio.refreshCatalog()}>Check again</button></p>}
          {catalog && !catalog.database_available && <p className="mb-3 text-xs text-red-700">Import the evidence database before starting research.</p>}
          {running ? <Button type="button" onClick={studio.stop} className="w-full"><Square />Stop research</Button> : <Button type="submit" variant="primary" className="h-10 w-full text-sm" disabled={!validInput || !catalog?.database_available || !catalog.connection_configured}><Search />Research and assess<ArrowRight /></Button>}
          <p className="mt-2 text-center text-2xs leading-4 text-slate-500">Selected redacted excerpts go to OpenAI; public questions go to web search. API charges may apply.</p>
        </div>
      </form>

      <div className="min-w-0 space-y-4">
        {(running || steps.length > 0 || error) && <section className="rounded-md border border-slate-200 bg-white p-4 shadow-sm" aria-label="Research progress" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2.5">{running ? <span className="inline-flex size-8 items-center justify-center rounded-md bg-brand-soft text-brand"><LoaderCircle className="size-4 animate-spin" /></span> : result ? <span className="inline-flex size-8 items-center justify-center rounded-md bg-emerald-50 text-emerald-700"><CheckCircle2 className="size-4" /></span> : null}<div><p className="text-xs font-semibold text-zinc-900">{running ? "Research in progress" : error ? "Research stopped" : "Decision brief ready"}</p><p className="text-2xs text-slate-500">{steps.length ? `${steps.length} completed updates` : "Preparing the scoped evidence"}</p></div></div>
            {result && <Button size="sm" variant="ghost" type="button" onClick={startOver}>Start a new decision</Button>}</div>
          {steps.length > 0 && <ol className="mt-4 space-y-0 border-l border-slate-200 pl-4 text-xs text-slate-600">{steps.map((step, index) => <li key={`${index}-${step}`} className="relative pb-3 last:pb-0"><span aria-hidden className="absolute -left-[21px] top-1 size-2.5 rounded-full border-2 border-white bg-brand" /><span className="font-mono text-2xs text-slate-400">{String(index + 1).padStart(2, "0")}</span><span className="ml-2">{step}</span></li>)}</ol>}
          {error && <p role="alert" className="mt-3 rounded-md border border-red-100 bg-red-50 p-3 text-xs text-red-800">{error}</p>}
        </section>}
        {result ? <AdvisorReport result={result} /> : !running && !error ? <StudioWelcome /> : running && <div className="rounded-md border border-slate-200 bg-white p-5" aria-hidden><div className="h-3 w-28 animate-pulse rounded-full bg-slate-100" /><div className="mt-4 h-6 w-3/4 animate-pulse rounded bg-slate-100" /><div className="mt-3 h-3 w-full animate-pulse rounded bg-slate-100" /><div className="mt-2 h-3 w-5/6 animate-pulse rounded bg-slate-100" /><div className="mt-6 grid grid-cols-2 gap-3"><div className="h-28 animate-pulse rounded-md bg-slate-100" /><div className="h-28 animate-pulse rounded-md bg-slate-100" /></div></div>}
      </div>
    </div>
  </div>;
}
