import "server-only";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { createInterface } from "node:readline";
import type { Operation } from "./contracts";

const runtimeState = globalThis as typeof globalThis & { advisorRunning?: boolean };
const headers = { "Content-Type": "application/x-ndjson; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
const jsonError = (message: string, status: number) => Response.json({message}, {status, headers: {"Cache-Control": "no-store"}});

function stopWorker(child: ChildProcessWithoutNullStreams) {
  if (child.exitCode !== null || !child.pid) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {windowsHide: true, stdio: "ignore"});
  } else child.kill("SIGTERM");
}

export async function advisorResponse(request: Request, operation: Operation): Promise<Response> {
  const url = new URL(request.url);
  let publicUrl: URL;
  try { publicUrl = new URL(`${url.protocol}//${request.headers.get("host") || url.host}`); }
  catch { return jsonError("Invalid local address.", 403); }
  if (!["localhost", "127.0.0.1", "[::1]"].includes(publicUrl.hostname)) return jsonError("Decision Studio is configured for local use.", 403);
  const origin = request.headers.get("origin");
  if (origin && origin !== publicUrl.origin) return jsonError("Use Decision Studio from the same local address.", 403);
  if (request.method === "POST" && !request.headers.get("content-type")?.startsWith("application/json")) return jsonError("Send a JSON request.", 415);
  let input = "{}";
  if (request.method === "POST") {
    if (Number(request.headers.get("content-length") || 0) > 1048576) return jsonError("The request exceeds 1 MB.", 413);
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) {
      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 1048576) { await reader.cancel(); return jsonError("The request exceeds 1 MB.", 413); }
        chunks.push(value);
      }
    }
    input = Buffer.concat(chunks).toString("utf8");
    try { const body: unknown = JSON.parse(input); if (!body || Array.isArray(body) || typeof body !== "object") throw new Error(); }
    catch { return jsonError("Send a JSON object.", 400); }
  }
  if (operation === "analyze" && runtimeState.advisorRunning) return jsonError("A research run is already active. Wait for it to finish or stop it first.", 409);
  const root = path.resolve(process.env.BMW_REPO_ROOT || path.resolve(process.cwd(), ".."));
  const localPython = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const python = process.env.BMW_PYTHON || localPython;
  if (!existsSync(python)) return jsonError("The Python environment is missing. Install the repository's ai dependencies or set BMW_PYTHON.", 503);
  if (operation === "analyze") runtimeState.advisorRunning = true;
  let child: ChildProcessWithoutNullStreams;
  let finish: (() => void) | undefined;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      let closed = false;
      let terminal = false;
      let outputBytes = 0;
      const send = (value: unknown) => { if (!closed) controller.enqueue(encoder.encode(JSON.stringify(value) + "\n")); };
      const abort = () => { stopWorker(child); finish?.(); };
      const timer = setTimeout(() => {
        send({type: "error", message: "Research exceeded the ten-minute limit. Try a narrower question."});
        abort();
      }, 600000);
      finish = () => {
        if (closed) return;
        closed = true;
        clearTimeout(timer);
        request.signal.removeEventListener("abort", abort);
        if (operation === "analyze") runtimeState.advisorRunning = false;
        // A disconnected browser may already have cancelled the stream.
        try { controller.close(); } catch { /* cancellation already closed it */ }
      };
      child = spawn(python, ["-m", "bmw_pm.advisor.bridge", operation], {
        cwd: root, windowsHide: true, shell: false,
        env: {...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1",
          PYTHONPATH: [path.join(root, "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)},
      });
      child.stderr.resume(); // Provider exceptions can include secrets; never forward raw stderr.
      child.stdin.on("error", () => {});
      child.on("error", () => { send({type: "error", message: "The Python advisor could not start."}); finish?.(); });
      const lines = createInterface({input: child.stdout});
      lines.on("line", (line) => {
        outputBytes += Buffer.byteLength(line);
        if (outputBytes > 16000000) { send({type: "error", message: "The result exceeded the response limit."}); abort(); return; }
        try {
          const event = JSON.parse(line) as {type?: string};
          if (!event.type || !["progress", "error", "result", "catalog", "sync", "scenarios", "memory"].includes(event.type)) throw new Error();
          if (event.type !== "progress") terminal = true;
          send(event);
        } catch { send({type: "error", message: "The advisor returned an invalid response."}); abort(); }
      });
      child.on("close", () => {
        if (!terminal) send({type: "error", message: "The advisor stopped before returning a result."});
        finish?.();
      });
      request.signal.addEventListener("abort", abort, {once: true});
      if (request.signal.aborted) abort();
      else child.stdin.end(input);
    },
    cancel() { if (child) stopWorker(child); finish?.(); },
  });
  return new Response(stream, {headers});
}
