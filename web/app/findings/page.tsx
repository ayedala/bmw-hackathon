import { Suspense } from "react";

import { TableSkeleton } from "@/components/app/data-table";
import { FindingsScreen } from "@/components/screens/findings";

export const metadata = { title: "Findings · BMW Product Decision Lab" };

export default function Page() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} columns={10} />}>
      <FindingsScreen />
    </Suspense>
  );
}
