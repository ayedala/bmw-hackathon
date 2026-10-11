import { Suspense } from "react";

import { TableSkeleton } from "@/components/app/data-table";
import { NeedsScreen } from "@/components/screens/needs";

export const metadata = { title: "Customer needs · BMW Product Decision Lab" };

export default function Page() {
  return <Suspense fallback={<TableSkeleton rows={8} columns={6} />}><NeedsScreen /></Suspense>;
}
