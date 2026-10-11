import "server-only";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  REVIEW_ACTIONS,
  STATUS_FOR_CODE,
  type ReviewAction,
  type ReviewError,
  type ReviewResult,
} from "./contracts";

/**
 * Bridge to the Python review service.
 *
 * PM decisions used to live in browser storage, which made the browser the
 * authority: a decision existed in one tab, produced no audit event, and could
 * not be refused for acting on a stale revision. Every write now goes to
 * bmw_pm.review.ReviewService through this process boundary.
 *
 * Nothing here decides anything. It validates the transport, runs the bridge
 * and maps the typed error code onto an HTTP status, so the review rules stay
 * in one place.
 */

const MAX_REQUEST_BYTES = 1_048_576;
const MAX_RESPONSE_BYTES = 16_000_000;
const TIMEOUT_MS = 30_000;

const NO_STORE = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };

function fail(code: ReviewError["code"], message: string): Response {
  return Response.json({ type: "error", code, message } satisfies ReviewError, {
    status: STATUS_FOR_CODE[code],
    headers: NO_STORE,
  });
}

/** Repository root, matching the advisor bridge's resolution. */
function repoRoot(): string {
  return path.resolve(process.env.BMW_REPO_ROOT || path.resolve(process.cwd(), ".."));
}

/**
 * Interpreter to run the bridge with.
 *
 * BMW_PYTHON wins, then the repository virtualenv. Unlike the advisor bridge
 * this falls back to python3 on PATH, because the review actions are part of
 * the main workflow and a checkout without a .venv should still be able to
 * record an audited decision.
 */
function resolvePython(root: string): string | null {
  if (process.env.BMW_PYTHON) {
    return existsSync(process.env.BMW_PYTHON) ? process.env.BMW_PYTHON : null;
  }
  const venv = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  if (existsSync(venv)) return venv;
  return "python3";
}

async function readBody(request: Request): Promise<string | Response> {
  if (request.method !== "POST") return "{}";
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return fail("invalid_request", "Send a JSON request.");
  }
  if (Number(request.headers.get("content-length") || 0) > MAX_REQUEST_BYTES) {
    return fail("invalid_request", "The request exceeds 1 MB.");
  }
  const reader = request.body?.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  if (reader) {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_REQUEST_BYTES) {
        await reader.cancel();
        return fail("invalid_request", "The request exceeds 1 MB.");
      }
      chunks.push(value);
    }
  }
  const text = Buffer.concat(chunks).toString("utf8") || "{}";
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error();
  } catch {
    return fail("invalid_request", "Send a JSON object.");
  }
  return text;
}

/** Run one bridge action and return its single result event. */
function runBridge(action: ReviewAction, input: string): Promise<ReviewResult> {
  const root = repoRoot();
  const python = resolvePython(root);
  if (!python) {
    return Promise.resolve({
      type: "error",
      code: "backend_unavailable",
      message: "BMW_PYTHON points at a path that does not exist.",
    });
  }

  return new Promise((resolve) => {
    let settled = false;
    const done = (result: ReviewResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };

    const child = spawn(python, ["-m", "bmw_pm.review.bridge", action], {
      cwd: root,
      windowsHide: true,
      shell: false,
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: [path.join(root, "src"), process.env.PYTHONPATH]
          .filter(Boolean)
          .join(path.delimiter),
      },
    });

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      done({
        type: "error",
        code: "backend_unavailable",
        message: "The review action did not finish within 30 seconds.",
      });
    }, TIMEOUT_MS);

    // Tracebacks can name local paths and configuration; never forward them.
    child.stderr.resume();
    child.stdin.on("error", () => {});
    child.on("error", () =>
      done({
        type: "error",
        code: "backend_unavailable",
        message: "The Python review service could not start.",
      }),
    );

    let stdout = "";
    let bytes = 0;
    child.stdout.on("data", (chunk: Buffer) => {
      bytes += chunk.byteLength;
      if (bytes > MAX_RESPONSE_BYTES) {
        child.kill("SIGTERM");
        done({
          type: "error",
          code: "internal",
          message: "The review result exceeded the response limit.",
        });
        return;
      }
      stdout += chunk.toString("utf8");
    });

    child.on("close", () => {
      const lines = stdout.split("\n").filter((line) => line.trim());
      if (!lines.length) {
        done({
          type: "error",
          code: "internal",
          message: "The review service returned nothing.",
        });
        return;
      }
      // The bridge emits one event per action; the last line is the outcome.
      const last = lines[lines.length - 1] ?? "";
      try {
        const event = JSON.parse(last) as ReviewResult;
        if (!event?.type) throw new Error();
        done(event);
      } catch {
        done({
          type: "error",
          code: "internal",
          message: "The review service returned an invalid response.",
        });
      }
    });

    child.stdin.end(input);
  });
}

export async function reviewResponse(request: Request, action: string): Promise<Response> {
  if (!(REVIEW_ACTIONS as readonly string[]).includes(action)) {
    return fail("invalid_request", `Unknown review action: ${action}`);
  }
  const body = await readBody(request);
  if (body instanceof Response) return body;

  const result = await runBridge(action as ReviewAction, body);
  const status = result.type === "error" ? STATUS_FOR_CODE[result.code] : 200;
  return Response.json(result, { status, headers: NO_STORE });
}
