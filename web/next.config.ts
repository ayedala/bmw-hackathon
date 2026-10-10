import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Self-contained server bundle, used by the desktop app (electron/main.cjs).
  output: "standalone",
  outputFileTracingRoot: path.resolve(__dirname),
};

export default nextConfig;
