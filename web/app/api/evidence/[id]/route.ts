import { loadDataset } from "@/lib/data/load";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const url = new URL(request.url);
  if (!["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
    return Response.json({ message: "This evidence view is local only." }, { status: 403 });
  }
  const { id } = await context.params;
  const dataset = await loadDataset();
  const evidence = dataset.evidence.find((item) => item.id === id);
  if (!evidence || evidence.raw === undefined) {
    return Response.json({ message: "Stored record not found." }, { status: 404 });
  }
  return Response.json({ raw: evidence.raw }, { headers: { "Cache-Control": "private, no-store" } });
}
