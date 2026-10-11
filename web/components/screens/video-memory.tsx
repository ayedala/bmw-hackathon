"use client";
import {useState, type FormEvent} from "react";
import {BookOpen, RefreshCw, Upload} from "lucide-react";
import {PageHeader, Metric, MetricStrip} from "@/components/app/layout-parts";
import {Button} from "@/components/ui/button";
import {callAdvisor} from "@/lib/advisor/client";
import {MARKETS, VEHICLES, type Vehicle} from "@/lib/advisor/contracts";
import {useStudio} from "@/lib/advisor/store";
import {fieldClass, labelClass} from "./decision-studio";

export function VideoMemoryScreen() {
  const studio = useStudio();
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [vehicle, setVehicle] = useState<Vehicle>("G60");
  const [market, setMarket] = useState("");
  const [transcript, setTranscript] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setNotice(""); setError("");
    try {
      await callAdvisor("memory", {title, video_url: url, model_code: vehicle, market: market || null, transcript}, event => {
        if (event.type === "memory") {
          studio.setCatalog(event.catalog);
          setNotice(event.memory.inserted ? `Transcript saved. ${event.memory.characters.toLocaleString()} characters are available to future decisions for ${VEHICLES[vehicle]}.` : "This transcript is already in memory. Repeated saves do not create extra evidence.");
          setTranscript("");
        }
      });
    } catch (e) {setError(e instanceof Error ? e.message : "The transcript could not be saved.");} finally {setBusy(false);}
  }
  async function sync() {
    setBusy(true); setError(""); setNotice("");
    try {
      await callAdvisor("sync", {}, event => {
        if (event.type === "sync") {
          studio.setCatalog(event.catalog);
          setNotice(`Checked ${event.sync.runs} saved runs: ${event.sync.inserted} new validated findings, ${event.sync.memories_inserted} new transcript memories, ${event.sync.rejected} rejected findings, ${event.sync.failed_runs} unreadable runs.`);
        }
      });
    } catch (e) {setError(e instanceof Error ? e.message : "Saved research could not be imported.");} finally {setBusy(false);}
  }
  return <>
    <PageHeader title="Video memory" question="Save a transcript once. Reuse it as supporting evidence in future BMW decisions."
      actions={<Button disabled={busy} onClick={() => void sync()}><RefreshCw />Import saved research</Button>} />
    <MetricStrip className="mb-5 grid-cols-3"><Metric label="Stored video transcripts" value={studio.catalog?.video_memories ?? "—"} /><Metric label="Validated video findings" value={studio.catalog?.youtube_findings ?? "—"} /><Metric label="Saved collector runs" value={studio.catalog?.saved_youtube_runs ?? "—"} /></MetricStrip>
    {notice && <p role="status" className="mb-4 rounded-md border border-brand-line bg-brand-soft p-3 text-xs text-brand">{notice}</p>}
    {(error || studio.catalogError) && <p role="alert" className="mb-4 rounded-md bg-red-50 p-3 text-xs text-red-700">{error || studio.catalogError}</p>}
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
      <form onSubmit={save} className="space-y-4 rounded-md border border-slate-200 bg-white p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><Upload className="size-4 text-brand" />Add an existing transcript</h2>
        <p className="text-xs leading-relaxed text-slate-500">Use this path when YouTube discovery quota is unavailable. Saving a transcript makes no YouTube or AI request.</p>
        <fieldset disabled={busy} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2"><label><span className={labelClass}>YouTube video URL</span><input className={fieldClass} type="url" required maxLength={500} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" /></label>
          <label><span className={labelClass}>Video title</span><input className={fieldClass} required maxLength={300} value={title} onChange={e => setTitle(e.target.value)} placeholder="A title to recognize this source" /></label></div>
          <div className="grid grid-cols-2 gap-3"><label><span className={labelClass}>BMW generation discussed</span><select className={fieldClass} value={vehicle} onChange={e => setVehicle(e.target.value as Vehicle)}>{Object.entries(VEHICLES).map(([id, label]) => <option key={id} value={id}>{label} · {id}</option>)}</select></label>
            <label><span className={labelClass}>Verified market (optional)</span><select className={fieldClass} value={market} onChange={e => setMarket(e.target.value)}><option value="">Unknown / not established</option>{Object.entries(MARKETS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label></div>
          <label className="block"><span className={labelClass}>Load a transcript file (.txt, .vtt or .srt)</span><input className="block w-full text-xs text-slate-500 file:mr-3 file:rounded-md file:border file:border-slate-200 file:bg-white file:px-3 file:py-1.5 file:text-xs" type="file" accept=".txt,.vtt,.srt,text/plain" onChange={async e => {
            const file = e.target.files?.[0]; if (!file) return;
            if (file.size > 800000) {setError("Choose a transcript file smaller than 800 KB."); return;}
            const text = await file.text(); if (text.length > 200000) {setError("The transcript must contain at most 200,000 characters."); return;}
            setTranscript(text); setError("");
          }} /></label>
          <label className="block"><span className={labelClass}>Transcript text</span><textarea className={fieldClass} rows={13} required minLength={50} maxLength={200000} value={transcript} onChange={e => setTranscript(e.target.value)} placeholder="Paste the actual transcript, including timestamps if available." /></label>
          <p className="text-2xs text-slate-500">{transcript.length.toLocaleString()} / 200,000 characters. Keep the source’s wording; interpretations belong in the decision brief.</p>
          <Button type="submit" variant="primary"><BookOpen />{busy ? "Saving…" : "Save transcript to memory"}</Button>
        </fieldset>
      </form>
      <aside className="space-y-5 rounded-md border border-slate-200 bg-white p-5"><h2 className="text-sm font-semibold">How memory helps</h2>
        <div><h3 className="mb-1 text-xs font-semibold">Persistent evidence</h3><p className="text-xs leading-relaxed text-slate-500">The transcript stays in the local database with its video link, supplied scope and original text. New versions retain earlier source history.</p></div>
        <div><h3 className="mb-1 text-xs font-semibold">Relevant excerpts</h3><p className="text-xs leading-relaxed text-slate-500">The agent selects generation-matched passages relevant to your question. The report explains the selection and links back to the source.</p></div>
        <div><h3 className="mb-1 text-xs font-semibold">Saved collector runs</h3><p className="text-xs leading-relaxed text-slate-500">Import saved research to validate quotes and retain retrieved transcripts, including those with no extracted findings. Research repeats this sync automatically.</p></div>
        <div className="border-t border-slate-100 pt-4 text-xs leading-relaxed text-slate-500">A video’s search region does not establish its market. Transcript claims remain reviewable, and repeated excerpts never become additional customers.</div>
      </aside>
    </div>
  </>;
}
