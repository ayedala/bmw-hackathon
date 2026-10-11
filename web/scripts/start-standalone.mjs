// Run the same standalone bundle used by the desktop app, bound to this machine.
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import "./prepare-standalone.mjs";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
process.env.BMW_REPO_ROOT ||= path.resolve(webRoot, "..");
process.env.HOSTNAME = "127.0.0.1";
process.env.PORT ||= "3000";

await import(pathToFileURL(path.join(webRoot, ".next", "standalone", "server.js")).href);
