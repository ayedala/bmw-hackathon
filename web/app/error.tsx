"use client";

import { Button } from "@/components/ui/button";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="max-w-xl rounded-md border border-slate-200 bg-white p-4" role="alert">
      <p className="text-[13px] font-medium text-zinc-900">This view could not be rendered from the current dataset.</p>
      <p className="mt-1 text-xs text-slate-500">
        A record may be missing a field the view expects. Check that the evidence files under external_research_pipeline/data and
        configs/ are valid JSON, then retry.
      </p>
      <p className="mt-2 font-mono text-2xs text-slate-500">{error.digest ?? error.message}</p>
      <Button className="mt-3" size="sm" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
