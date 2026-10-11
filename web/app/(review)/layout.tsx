import type { ReactNode } from "react";

import { AppShell } from "@/components/app/shell";
import { loadDataset } from "@/lib/data/load";
import { StoreProvider } from "@/lib/store";
import { StudioProvider } from "@/lib/advisor/store";

export const dynamic = "force-dynamic";

export default async function ReviewLayout({ children }: { children: ReactNode }) {
  const dataset = await loadDataset();
  // Exact source records remain server-side until a reviewer opens one.
  const initialDataset = {
    ...dataset,
    evidence: dataset.evidence.map((evidence) => {
      const item = { ...evidence };
      delete item.raw;
      return item;
    }),
  };
  return (
    <StoreProvider dataset={initialDataset}>
      <StudioProvider><AppShell>{children}</AppShell></StudioProvider>
    </StoreProvider>
  );
}
