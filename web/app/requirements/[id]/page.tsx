import { RequirementWorkspace } from "@/components/screens/requirement-workspace";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return { title: `${id} · BMW Product Decision Lab` };
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RequirementWorkspace displayId={decodeURIComponent(id)} />;
}
