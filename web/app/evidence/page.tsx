import { Suspense } from "react";

import { TableSkeleton } from "@/components/app/data-table";
import { EvidenceExplorer } from "@/components/screens/evidence-explorer";

export const metadata = { title: "Evidence · BMW Product Decision Lab" };

export default function Page() {
  return (
    <Suspense fallback={<TableSkeleton rows={12} columns={9} />}>
      <EvidenceExplorer />
    </Suspense>
  );
}
