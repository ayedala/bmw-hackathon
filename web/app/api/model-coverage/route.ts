import path from "node:path";
import { loadLiveSnapshot } from "@/lib/data/live";

export const dynamic = "force-dynamic";

export async function GET() {
  const root = process.env.BMW_REPO_ROOT ?? path.resolve(process.cwd(), "..");
  const snapshot = await loadLiveSnapshot(root);
  return Response.json({ available: snapshot.available, reason: snapshot.reason ?? null,
    coverage: snapshot.model_coverage ?? [] });
}
