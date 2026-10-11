"use client";

import { Button } from "@/components/ui/button";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const chunkLoadFailed = /loading chunk|chunkloaderror|failed to fetch dynamically imported module/i.test(error.message);

  return (
    <div className="max-w-xl rounded-md border border-slate-200 bg-white p-4" role="alert">
      <p className="text-[13px] font-medium text-zinc-900">
        {chunkLoadFailed ? "The page script could not load." : "This view could not be loaded."}
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {chunkLoadFailed
          ? "The app may have restarted while this browser tab held an older build. Reload the page to request the current files."
          : "Try again. If the problem continues, check the app server logs and data connection."}
      </p>
      {error.digest && <p className="mt-2 font-mono text-2xs text-slate-500">Error ID: {error.digest}</p>}
      <Button className="mt-3" size="sm" onClick={chunkLoadFailed ? () => window.location.reload() : reset}>
        {chunkLoadFailed ? "Reload page" : "Retry"}
      </Button>
    </div>
  );
}
