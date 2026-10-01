import { ApiError, tokens } from "./api";
import type { ChatRequest, SseEvent } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function* streamChat(
  body: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
    cache: "no-store",
  });

  // Failures known before the first frame arrive as a normal HTTP envelope.
  if (!res.ok) throw await (async () => {
    const env = await res.json().catch(() => null);
    return new ApiError(
      res.status,
      env?.error?.code ?? "internal",
      env?.error?.message ?? `Chat failed (${res.status})`,
      env?.error?.retryable ?? false,
      env?.error?.details,
    );
  })();
  if (!res.body) throw new ApiError(500, "internal", "Empty stream response");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const parseBlock = (block: string): SseEvent | null => {
    const lines = block.split("\n");
    const eventLine = lines.find((l) => l.startsWith("event: "));
    const dataLine = lines.find((l) => l.startsWith("data: "));
    if (!eventLine || !dataLine) return null;
    const event = eventLine.slice(7).trim();
    const data = JSON.parse(dataLine.slice(6));
    return { event, data } as SseEvent;
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        if (!block.trim()) continue;
        const parsed = parseBlock(block);
        if (parsed) yield parsed;
      }
    }
  } finally {
    reader.releaseLock();
  }
  // Note: the terminal invariant guarantees you already saw exactly one
  // "done" or "error" before the generator ends. If the connection died
  // first, treat it as a retryable network error in the caller.
}
