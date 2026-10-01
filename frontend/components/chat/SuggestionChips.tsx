"use client";

import { ChevronRight } from "lucide-react";

interface SuggestionChipsProps {
  suggestions: string[];
  onPick: (question: string) => void;
  disabled?: boolean;
}

/** "Want to go deeper?" follow-up chips above the composer (§1, §8.5).
 *  Clicking a chip sends it immediately. */
export function SuggestionChips({ suggestions, onPick, disabled = false }: SuggestionChipsProps) {
  if (suggestions.length === 0) return null;

  return (
    <div className="border-t border-border bg-background/70 px-3 pt-2.5 pb-1 md:px-4">
      <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-muted">Want to go deeper?</span>
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            disabled={disabled}
            onClick={() => onPick(s)}
            className="inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:border-brand/50 hover:bg-indigo-50 hover:text-brand disabled:cursor-not-allowed disabled:opacity-60 bw-compact"
          >
            <ChevronRight className="size-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate">{s}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
