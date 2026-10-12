import { SuggestedRequirementReview } from "@/components/screens/suggested-requirement-review";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SuggestedRequirementReview id={decodeURIComponent(id)} />;
}
