import type { Metadata } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";

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

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={plex.variable}>
      <body>{children}</body>
    </html>
  );
}
