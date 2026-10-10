import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div aria-busy="true" aria-label="Loading">
      <Skeleton className="h-5 w-56" />
      <Skeleton className="mt-2 h-3 w-80" />
      <div className="mt-5 grid grid-cols-6 gap-px overflow-hidden rounded-md border border-slate-200/60 bg-slate-200/60">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="bg-white px-3 py-2.5">
            <Skeleton className="h-2 w-16" />
            <Skeleton className="mt-2 h-5 w-10" />
          </div>
        ))}
      </div>
      <div className="mt-5 space-y-2 rounded-md border border-slate-200/60 bg-white p-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-4 w-full" />
        ))}
      </div>
    </div>
  );
}
