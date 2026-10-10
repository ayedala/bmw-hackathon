import { Suspense } from "react";

import { TableSkeleton } from "@/components/app/data-table";
import { HypothesesScreen } from "@/components/screens/hypotheses";

export const metadata = { title: "Hypotheses · BMW Product Decision Lab" };

export default function Page() {
  return (
    <Suspense fallback={<TableSkeleton />}>
      <HypothesesScreen />
    </Suspense>
  );
}
