import type { ReactNode } from "react";

import { decisionStatus, latestRevision } from "@/lib/domain/derive";
import { AppShell } from "@/components/app/shell";
import { loadDataset } from "@/lib/data/load";
import { StoreProvider } from "@/lib/store";
import { StudioProvider } from "@/lib/advisor/store";

export const dynamic = "force-dynamic";

export default async function StudioLayout({ children }: { children: ReactNode }) {
  const dataset = await loadDataset();
  // Studio research runs through its own API. Keep review evidence off the initial page.
  const summary = {
    findings: dataset.findings.length,
    evidence: dataset.evidence.length,
    requirements: dataset.requirements.length,
    openDecisions: dataset.requirements.filter((r) => {
      const status = decisionStatus(latestRevision(r), r.decisions);
      return status === "under_review" || status === "challenged" || status === "draft";
    }).length,
  };
  const initialDataset = {
    ...dataset,
    evidence: [], requirements: [], findings: [], hypotheses: [],
    model_coverage: [], planning_context: [], benchmark: [], audit: [],
    research_runs: [], data_notes: [], source_files: [],
  };
  return (
    <StoreProvider dataset={initialDataset}>
      <StudioProvider>
        <AppShell summary={summary}>{children}</AppShell>
      </StudioProvider>
    </StoreProvider>
  );
}
