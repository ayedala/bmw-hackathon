import type { Metadata } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app/shell";
import { loadDataset } from "@/lib/data/load";
import { StoreProvider } from "@/lib/store";
import { StudioProvider } from "@/lib/advisor/store";

import "./globals.css";

// IBM Plex Sans (SIL Open Font License, see app/fonts/OFL.txt) — the same face as the Streamlit workbench.
const plex = localFont({
  src: "./fonts/ibm-plex-sans.ttf",
  variable: "--font-plex",
  weight: "100 700",
  display: "swap",
});

export const metadata: Metadata = {
  title: "BMW Product Decision Lab",
  description: "Successor requirement decisions for BMW product management — evidence, priority and audit in one place.",
};

// Evidence files are read from the repository on each request so new pipeline runs show up without a rebuild.
export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: ReactNode }) {
  const dataset = await loadDataset();
  return (
    <html lang="en" className={plex.variable}>
      <body>
        <StoreProvider dataset={dataset}>
          <StudioProvider><AppShell>{children}</AppShell></StudioProvider>
        </StoreProvider>
      </body>
    </html>
  );
}
