"use client";

import { useState } from "react";

import { EmptyState, KeyValue, PageHeader, Section } from "@/components/app/layout-parts";
import { WeightControls } from "@/components/app/score";
import { Input, Label } from "@/components/ui/input";
import { FACTOR_HINT, FACTOR_LABEL, humanize } from "@/lib/domain/derive";
import { PRIORITY_FORMULA } from "@/lib/domain/scoring";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function SettingsScreen() {
  const { dataset, sessionEventCount, challenges, resetSession, actorId, setActorId } = useStore();
  const [confirm, setConfirm] = useState(false);
  const { policy, profile } = dataset;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        question="Which policy, profile and data does this workspace use?"
        meta={<span>Policy and profile are read from configs/ in the repository. Edit them there; this view is read-only.</span>}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Section title="Legacy planning priority method" description={`bmw_pm.decision.planning.priority_score · ${PRIORITY_FORMULA}`}>
          <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
            <table className="w-full text-[13px]">
              <caption className="sr-only">Priority factors</caption>
              <thead>
                <tr className="border-b border-slate-200 text-2xs uppercase tracking-wide text-slate-500">
                  <th scope="col" className="h-8 px-4 text-left font-medium">Factor</th>
                  <th scope="col" className="px-3 text-right font-medium">Default weight</th>
                  <th scope="col" className="px-3 text-left font-medium">Rating anchors (0–4)</th>
                </tr>
              </thead>
              <tbody>
                {(Object.keys(FACTOR_LABEL) as (keyof typeof FACTOR_LABEL)[]).map((k) => (
                  <tr key={k} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-1.5 font-medium text-zinc-900">{FACTOR_LABEL[k]}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{{ impact: "0.35", evidence: "0.25", relevance: "0.25", uncertainty: "0.15" }[k]}</td>
                    <td className="px-3 py-1.5 text-xs text-slate-600">{FACTOR_HINT[k]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-2xs text-slate-500">Ratings are declared PM judgements, not measured prevalence or calibrated confidence. Seed ratings come from {dataset.planning.version}.</p>
        </Section>
        <div className="space-y-4">
          <div className="rounded-md border border-slate-200 bg-white p-3">
            <WeightControls />
          </div>
          <div className="rounded-md border border-slate-200 bg-white p-3">
            <Label htmlFor="settings-reviewer">Reviewer ID</Label>
            <Input id="settings-reviewer" value={actorId} onChange={(e) => setActorId(e.target.value)} className="mt-1" />
            <p className="mt-1 text-2xs text-slate-500">Recorded on every assessment, decision and audit event from this device. Not authenticated.</p>
          </div>
        </div>
      </div>

      <Section title={`Decision-engine value policy · ${policy.policy_id} r${policy.revision}`} description={`${policy.name} — used by bmw_pm.decision.scoring for corpus-based value intervals.`}>
        <div className="rounded-md border border-slate-200/60 bg-white">
          <dl className="grid gap-4 border-b border-slate-200/60 p-4 md:grid-cols-4">
            <KeyValue label="Approved">{policy.approved ? "Yes" : <span className="text-amber-700">No — exploratory</span>}</KeyValue>
            <KeyValue label="Saturation share">{(policy.saturation_share * 100).toFixed(1)}%</KeyValue>
            <KeyValue label="Unknown rule" className="md:col-span-2">
              <span className="text-xs">{policy.unknown_rule}</span>
            </KeyValue>
            <KeyValue label="Elicitation record" className="md:col-span-4">
              <span className="text-xs">{policy.elicitation_record}</span>
            </KeyValue>
          </dl>
          <table className="w-full text-[13px]">
            <caption className="sr-only">Policy criteria</caption>
            <thead>
              <tr className="border-b border-slate-200/70 text-2xs uppercase tracking-wide text-slate-500">
                <th scope="col" className="h-8 px-4 text-left font-medium">Criterion</th>
                <th scope="col" className="px-3 text-left font-medium">Dimension</th>
                <th scope="col" className="px-3 text-right font-medium">Weight</th>
                <th scope="col" className="px-3 text-left font-medium">Anchor 0</th>
                <th scope="col" className="px-3 text-left font-medium">Anchor 4</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(policy.criteria).map(([key, c]) => (
                <tr key={key} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-1.5 font-medium text-zinc-900">{humanize(key)}</td>
                  <td className="px-3 py-1.5 text-xs text-slate-600">{c.dimension}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{c.weight.toFixed(2)}</td>
                  <td className="px-3 py-1.5 text-xs text-slate-600">{c.anchor_0}</td>
                  <td className="px-3 py-1.5 text-xs text-slate-600">{c.anchor_4}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title={`Vehicle profile · ${profile.profile_id} r${profile.revision}`}>
          <dl className="grid grid-cols-2 gap-4 rounded-md border border-slate-200/60 bg-white p-4">
            <KeyValue label="Model family">{profile.model_family}</KeyValue>
            <KeyValue label="Feedback countries">{profile.countries.join(", ")}</KeyValue>
            <KeyValue label="Powertrains">{profile.powertrains.join(", ")}</KeyValue>
            <KeyValue label="Uncovered regions">{profile.uncovered_regions.join(", ") || "—"}</KeyValue>
            <KeyValue label="Planning date">{profile.planning_date}</KeyValue>
            <KeyValue label="Objectives">{profile.objectives.length ? profile.objectives.join("; ") : <span className="text-amber-700">None approved</span>}</KeyValue>
            <KeyValue label="Notes" className="col-span-2">
              <ul className="list-disc space-y-0.5 pl-4 text-xs text-slate-600">
                {profile.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </KeyValue>
          </dl>
        </Section>

        <Section title="Data sources">
          <ul className="divide-y divide-slate-100 rounded-md border border-slate-200/60 bg-white">
            {dataset.source_files.map((f) => (
              <li key={f.path} className="flex items-center justify-between gap-3 px-3 py-1.5 text-xs">
                <span className="truncate font-mono text-2xs text-zinc-800">{f.path}</span>
                <span className={cn("shrink-0", f.status === "loaded" ? "text-zinc-700" : "text-amber-700")}>
                  {f.status === "loaded" ? `${f.records} record${f.records === 1 ? "" : "s"}` : f.status}
                </span>
              </li>
            ))}
          </ul>
          <ul className="mt-2 list-disc space-y-0.5 pl-4 text-2xs text-slate-500">
            {dataset.data_notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Section>
      </div>

      <Section title="Local session" description="PM decisions, edits and challenges made in this browser.">
        {sessionEventCount === 0 ? (
          <EmptyState title="No PM actions recorded in this browser yet." />
        ) : (
          <div className="flex items-center justify-between rounded-md border border-slate-200/60 bg-white px-4 py-3">
            <span className="text-xs text-zinc-800">
              {sessionEventCount} audit events · {challenges.length} challenge{challenges.length === 1 ? "" : "s"}
            </span>
            <Button variant="destructive" size="sm" onClick={() => setConfirm(true)}>
              Reset local session
            </Button>
          </div>
        )}
      </Section>

      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent
          title="Reset local session?"
          description="Removes every decision, edit, challenge and audit event recorded in this browser."
          footer={
            <>
              <DialogClose asChild>
                <Button variant="ghost">Cancel</Button>
              </DialogClose>
              <Button
                variant="destructive"
                onClick={() => {
                  resetSession();
                  setConfirm(false);
                }}
              >
                Reset session
              </Button>
            </>
          }
        >
          <p className="text-xs text-slate-600">This cannot be undone. Export or screenshot the audit trail first if you need it.</p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
