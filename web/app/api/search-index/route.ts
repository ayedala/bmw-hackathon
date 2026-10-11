import { loadDataset } from "@/lib/data/load";
import { latestRevision } from "@/lib/domain/derive";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  if (!["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
    return Response.json({ message: "Search is local only." }, { status: 403 });
  }
  const dataset = await loadDataset();
  return Response.json({
    requirements: dataset.requirements.map((r) => ({ id: r.display_id, title: latestRevision(r).title, topic: r.topic })),
    findings: dataset.findings.map((f) => ({ id: f.id, title: f.title, market: f.market, topic: f.topic })),
    hypotheses: dataset.hypotheses.map((h) => ({ id: h.id, statement: h.statement })),
    evidence: dataset.evidence.map((e) => ({ id: e.id, claim: e.claim, vehicle: e.vehicle, market: e.market, source_name: e.source_name })),
    benchmark: dataset.benchmark.filter((b) => !b.is_reference).map((b) => ({ vehicle: b.vehicle })),
  }, { headers: { "Cache-Control": "private, no-store" } });
}
