"use client";

import { useStore } from "@/lib/store";

/**
 * Says where a PM action will actually be recorded.
 *
 * A decision written to the audited review database and one kept in browser
 * storage are not the same thing, and the difference is invisible unless the
 * UI says so. These two notices exist so nobody reads a session-only entry as
 * a committed decision.
 */

export function RecordingTarget({ displayId }: { displayId: string }) {
  const { backend, backendProbed, isBackendBacked, requirementByDisplayId } = useStore();

  if (!backendProbed) {
    return (
      <p className="rounded-sm bg-slate-50 px-2 py-1.5 text-xs text-zinc-600">
        Checking whether the review service can record this decision…
      </p>
    );
  }

  if (isBackendBacked(displayId)) {
    const bundle = requirementByDisplayId.get(displayId);
    const requirementId = bundle?.revisions[bundle.revisions.length - 1]?.requirement_id;
    const revision = requirementId ? backend.statesById.get(requirementId)?.revision : undefined;
    return (
      <p className="rounded-sm bg-emerald-50 px-2 py-1.5 text-xs text-emerald-900">
        Recorded in the audited review database against revision {revision}. The service
        refuses the action if someone else has edited this requirement meanwhile.
      </p>
    );
  }

  return (
    <p className="rounded-sm bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
      <span className="font-medium">Session only.</span>{" "}
      {backend.reachable
        ? "This requirement has no revision in the review database, so no audit event is written there and the entry exists in this browser only."
        : `The review service is unreachable (${backend.reason ?? "no reason given"}), so the entry exists in this browser only.`}
    </p>
  );
}

/** The last refusal from the review service, which must not pass silently. */
export function ReviewErrorNotice() {
  const { reviewError, clearReviewError } = useStore();
  if (!reviewError) return null;

  const heading =
    reviewError.code === "stale_revision"
      ? "Not recorded: this requirement changed"
      : reviewError.code === "request_conflict"
        ? "Not recorded: conflicting request"
        : reviewError.code === "backend_unavailable"
          ? "Not recorded: review service unavailable"
          : "Not recorded";

  return (
    <div className="rounded-sm border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-900">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium">{heading}</p>
          <p className="mt-0.5">{reviewError.message}</p>
          {reviewError.code === "stale_revision" && (
            <p className="mt-0.5">Reload the requirement and review the current revision before deciding again.</p>
          )}
        </div>
        <button
          type="button"
          onClick={clearReviewError}
          className="shrink-0 rounded-sm px-1 text-red-700 underline"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
