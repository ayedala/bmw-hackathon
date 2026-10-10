import { advisorResponse } from "@/lib/advisor/server";
import type { Operation } from "@/lib/advisor/contracts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) { return advisorResponse(request, "catalog"); }
export async function POST(request: Request) {
  const operation = new URL(request.url).searchParams.get("operation") || "analyze";
  if (!["analyze", "sync", "scenarios", "memory"].includes(operation)) return Response.json({message: "Unknown operation."}, {status: 400});
  return advisorResponse(request, operation as Operation);
}
