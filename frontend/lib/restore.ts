import type { Message, QuestionPayload } from "./types";

export type ViewItem =
  | { kind: "user"; message: Message }
  | { kind: "assistant-text"; message: Message }
  | { kind: "question"; message: Message; question: QuestionPayload; answered: boolean };

export function toViewItems(messages: Message[]): ViewItem[] {
  const items: ViewItem[] = [];
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.role === "user") { items.push({ kind: "user", message: m }); continue; }
    if (m.phase === "assessing") {
      try {
        const question = JSON.parse(m.content) as QuestionPayload;
        const next = messages[i + 1];
        const answered = next?.role === "user" && next.phase === "assessing";
        items.push({ kind: "question", message: m, question, answered });
      } catch {
        items.push({ kind: "assistant-text", message: m }); // defensive
      }
      continue;
    }
    items.push({ kind: "assistant-text", message: m });
  }
  return items;
}

/** True when history ends with an answer whose next question never arrived →
 *  re-submit the last answer (idempotent resume path, §5.5). */
export function pendingAnswer(messages: Message[]): { question_id: string; option: "A"|"B"|"C"|"D" } | null {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "user" || last.phase !== "assessing") return null;
  const prev = messages[messages.length - 2];
  if (!prev || prev.role !== "assistant" || prev.phase !== "assessing") return null;
  try {
    const q = JSON.parse(prev.content) as QuestionPayload;
    const entry = Object.entries(q.options).find(([, text]) => text === last.content);
    if (!entry) return null;
    return { question_id: q.question_id, option: entry[0] as "A" | "B" | "C" | "D" };
  } catch { return null; }
}
