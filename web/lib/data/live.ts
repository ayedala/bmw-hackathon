import "server-only";

import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

import type { Signal, SourceLocator } from "@/lib/domain/contracts";
import type { ModelCoverageSummary } from "@/lib/domain/model";

const execFileAsync = promisify(execFile);

export interface LiveFeedback {
  record_id: string;
  source_record_id: string;
  redacted_text: string;
  powertrain: string | null;
  row_locators: SourceLocator[];
}

export interface LiveSnapshot {
  available: boolean;
  reason?: string;
  backend?: "sqlite" | "postgres";
  eligible_feedback_records?: number;
  feedback?: LiveFeedback[];
  signals?: Signal[];
  model_coverage?: ModelCoverageSummary[];
}

let cached: { root: string; expires: number; value: LiveSnapshot } | null = null;
let loading: { root: string; promise: Promise<LiveSnapshot> } | null = null;

async function fetchLiveSnapshot(root: string): Promise<LiveSnapshot> {
  const localPython = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const python = process.env.BMW_PYTHON || (existsSync(localPython) ? localPython : "python");
  try {
    const { stdout } = await execFileAsync(python, [path.join(root, "scripts", "export_planning_snapshot.py")], {
      cwd: root,
      windowsHide: true,
      timeout: 12000,
      maxBuffer: 16 * 1024 * 1024,
    });
    const result = JSON.parse(stdout) as LiveSnapshot;
    const value = result.available && Array.isArray(result.feedback) && Array.isArray(result.signals)
      ? result
      : { available: false, reason: result.reason || "The evidence database is unavailable." };
    return value;
  } catch {
    return { available: false, reason: "The evidence database could not be read. Check Python and the database connection." };
  }
}

export function loadLiveSnapshot(root: string): Promise<LiveSnapshot> {
  if (cached && cached.root === root && cached.expires > Date.now()) return Promise.resolve(cached.value);
  if (loading?.root === root) return loading.promise;
  const promise = fetchLiveSnapshot(root).then((value) => {
    cached = { root, expires: Date.now() + (value.available ? 300000 : 15000), value };
    return value;
  }).finally(() => {
    if (loading?.promise === promise) loading = null;
  });
  loading = { root, promise };
  return promise;
}
