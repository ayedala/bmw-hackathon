// Copies static assets next to the standalone server so the desktop app can serve them.
import { cpSync, existsSync } from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const standalone = path.join(root, ".next", "standalone");
if (!existsSync(path.join(standalone, "server.js"))) {
  console.error("Standalone server missing. Run `next build` first.");
  process.exit(1);
}
cpSync(path.join(root, ".next", "static"), path.join(standalone, ".next", "static"), { recursive: true, force: true });
if (existsSync(path.join(root, "public"))) {
  cpSync(path.join(root, "public"), path.join(standalone, "public"), { recursive: true, force: true });
}
console.log("Standalone bundle ready:", standalone);
