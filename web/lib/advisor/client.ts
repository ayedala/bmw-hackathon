import type { Operation, StudioEvent } from "./contracts";

export async function callAdvisor(operation: Operation, payload: unknown, onEvent: (event: StudioEvent) => void, signal?: AbortSignal) {
  const response = await fetch(`/api/advisor?operation=${operation}`, operation === "catalog"
    ? {cache: "no-store", signal}
    : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload), signal});
  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as {message?: string};
    throw new Error(error.message || "The local advisor is unavailable. Try again.");
  }
  if (!response.body) throw new Error("The advisor returned no response.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let completed = false;
  const handle = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as StudioEvent;
    if (event.type === "error") throw new Error(event.message);
    if (event.type !== "progress") completed = true;
    onEvent(event);
  };
  try {
    while (true) {
      const {done, value} = await reader.read();
      pending += decoder.decode(value, {stream: !done});
      const lines = pending.split("\n");
      pending = lines.pop() || "";
      for (const line of lines) handle(line);
      if (done) break;
    }
    handle(pending);
    if (!completed) throw new Error("The research connection ended before a result was returned.");
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
