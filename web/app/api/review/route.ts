import { reviewResponse } from "@/lib/review/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Reads: current backend state and the audit chain. */
export async function GET(request: Request) {
  const action = new URL(request.url).searchParams.get("action") || "state";
  return reviewResponse(request, action);
}

/** Writes: every PM action goes through the Python review service. */
export async function POST(request: Request) {
  const action = new URL(request.url).searchParams.get("action") || "state";
  return reviewResponse(request, action);
}
