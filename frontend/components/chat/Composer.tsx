"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Send, Square } from "lucide-react";
import type { Phase } from "@/lib/types";

interface ComposerProps {
  phase: Phase;
  topicTitle: string;
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  disabled?: boolean;
}

function placeholderFor(phase: Phase, topicTitle: string): string {
  switch (phase) {
    case "topic_set":
      return "Press Send to start your assessment";
    case "assessing":
      return "Answer the question above to continue";
    case "scoring":
      return "Calculating your level…";
    case "explaining":
      return "Brainwise is explaining…";
    case "follow_up":
      return `Ask a follow-up about ${topicTitle || "this topic"}…`;
    default:
      return "Ask a follow-up…";
  }
}

/** Phase-aware composer (§8.5): disabled during assessing/scoring, Stop while streaming,
 *  Enter sends / Shift+Enter newline, 4000-char cap with amber counter >3600. */
export function Composer({ phase, topicTitle, streaming, onSend, onStop, disabled = false }: ComposerProps) {
  const [draft, setDraft] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);
  const readOnly = phase === "assessing" || phase === "scoring" || disabled;
  const tooLong = draft.length >= 4000;

  const send = () => {
    const text = draft.trim();
    if (!text || streaming || readOnly) return;
    setDraft("");
    if (taRef.current) taRef.current.style.height = "auto";
    onSend(text);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="border-t border-border bg-surface/95 p-3 backdrop-blur md:p-4">
      <div className="mx-auto flex w-full max-w-3xl items-end gap-2">
        <label htmlFor="composer-input" className="sr-only">
          Message
        </label>
        <textarea
          id="composer-input"
          ref={taRef}
          rows={1}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value.slice(0, 4000));
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholderFor(phase, topicTitle)}
          readOnly={readOnly}
          aria-disabled={readOnly}
          className="max-h-40 min-h-11 flex-1 resize-none rounded-2xl border border-border bg-background px-4 py-2.5 text-sm text-slate-900 outline-none transition-colors placeholder:text-muted focus:border-brand"
        />

        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            title="Stop"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-slate-700 transition-colors hover:border-danger/40 hover:text-danger"
          >
            <Square className="size-4 fill-current" aria-hidden="true" />
          </button>
        ) : (
          <button
            type="button"
            onClick={send}
            disabled={readOnly || draft.trim().length === 0}
            aria-label="Send message"
            title="Send"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand text-white transition-colors hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send className="size-4" aria-hidden="true" />
          </button>
        )}
      </div>

      <div className="mx-auto mt-1 flex w-full max-w-3xl justify-end">
        {draft.length > 3600 && (
          <span
            className={`text-xs tabular-nums ${tooLong ? "text-warning" : "text-amber-600"}`}
            aria-live="polite"
          >
            {draft.length}/4000
          </span>
        )}
      </div>
    </div>
  );
}
