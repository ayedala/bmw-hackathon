"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Section } from "@/components/app/layout-parts";
import { VEHICLES } from "@/lib/advisor/contracts";
import { decideSuggestedRequirement, useReviewDrafts } from "@/lib/advisor/review-drafts";

export function SuggestedRequirementReview({ id }: { id: string }) {
  const drafts = useReviewDrafts();
  const [ready, setReady] = useState(false);
  const [reviewer, setReviewer] = useState("");
  const [rationale, setRationale] = useState("");
  useEffect(() => setReady(true), []);
  const draft = drafts.find((item) => item.id === id);
  if (!ready) return <p className="p-4 text-sm">Loading suggested requirement…</p>;
  if (!draft) return <div className="space-y-4"><PageHeader title="Suggested requirement unavailable" question="This browser has no saved copy of the suggestion." /><Button asChild><Link href="/requirements">Back to requirements</Link></Button></div>;
  const valid = reviewer.trim().length > 0 && rationale.trim().length >= 5;
  const decide = (status: "approved" | "rejected") => {
    if (decideSuggestedRequirement(id, status, reviewer, rationale)) setRationale("");
  };
  return <div className="space-y-5">
    <nav className="text-xs"><Link href="/requirements" className="text-brand underline">Requirements</Link> / Suggested requirement</nav>
    <PageHeader title={draft.title} question={`${VEHICLES[draft.model_code]} · ${draft.market} · ${draft.powertrain}`} />
    <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-xs text-amber-950">Studio suggestion. PM decisions here are saved in this browser only; they are not part of the audited canonical review database.</div>
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="space-y-5">
        <Section title="Proposed requirement"><p className="text-sm leading-relaxed">{draft.proposal}</p></Section>
        <Section title="Customer outcome"><p className="text-sm leading-relaxed">{draft.customer_outcome}</p></Section>
        <Section title="Source context"><p className="text-xs">Studio run: <span className="font-mono">{draft.source_run_id}</span></p><p className="mt-2 text-xs">Evidence references: {draft.evidence_ids.length ? draft.evidence_ids.join(", ") : "None attached; review the source brief before approval."}</p></Section>
      </div>
      <aside className="space-y-4 rounded-md border border-slate-200 bg-white p-4 self-start">
        <h2 className="text-sm font-semibold">PM review</h2>
        <p className="text-xs">Status: <strong className="capitalize">{draft.status}</strong></p>
        {draft.reviewed_at && <p className="text-xs">{draft.reviewer_id} · {new Date(draft.reviewed_at).toLocaleString()}<br />{draft.rationale}</p>}
        <label className="block text-xs font-medium" htmlFor="suggestion-reviewer">Reviewer ID</label>
        <Input id="suggestion-reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="PM name or ID" />
        <label className="block text-xs font-medium" htmlFor="suggestion-rationale">Decision rationale</label>
        <textarea id="suggestion-rationale" value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="Explain the decision" rows={4} className="w-full rounded-md border border-slate-200 p-2 text-sm" />
        <div className="flex gap-2"><Button variant="primary" disabled={!valid} onClick={() => decide("approved")}>Approve</Button><Button variant="destructive" disabled={!valid} onClick={() => decide("rejected")}>Reject</Button></div>
      </aside>
    </div>
  </div>;
}
