import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
delete process.env.DATABASE_URL;
process.env.BMW_PM_DB_PATH ||= path.join(root, "data", "processed", "pm_review_local.sqlite");
await import("./start-standalone.mjs");
