import Link from "next/link";

export default function NotFound() {
  return (
    <div className="max-w-xl rounded-md border border-dashed border-slate-200 bg-white p-4">
      <p className="text-[13px] font-medium text-zinc-900">No record exists at this address.</p>
      <p className="mt-1 text-xs text-slate-500">The requirement may have been renamed, or the link points to an ID from another dataset.</p>
      <Link href="/requirements" className="mt-3 inline-block text-xs text-zinc-900 underline underline-offset-2">
        Go to requirements
      </Link>
    </div>
  );
}
