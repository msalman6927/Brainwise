"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Loader2 } from "lucide-react";
import { DifficultyBadge } from "@/components/Chips";
import type { OptionLetter, QuestionPayload } from "@/lib/types";

const LETTERS: OptionLetter[] = ["A", "B", "C", "D"];

interface McqCardProps {
  question: QuestionPayload;
  number: number;
  total: number;
  /** Option text the student picked (from a following user message), if answered. */
  answeredText?: string | null;
  /** True for the active unanswered question during `assessing`. */
  interactive: boolean;
  busy: boolean;
  onSubmit?: (letter: OptionLetter) => void;
  /** Bump on a live `question` event to move focus here (§8.6). */
  focusSignal?: number;
}

/** MCQ card: A–D option buttons, Submit, difficulty badge, no correctness reveal (§8.5).
 *  Keyboard: A–D / 1–4 select, Enter submits (§14.3). */
export function McqCard({
  question,
  number,
  total,
  answeredText = null,
  interactive,
  busy,
  onSubmit,
  focusSignal = 0,
}: McqCardProps) {
  const [selected, setSelected] = useState<OptionLetter | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const answered = answeredText !== null;
  const canPick = interactive && !answered && !busy;

  useEffect(() => {
    if (focusSignal > 0) cardRef.current?.focus();
  }, [focusSignal]);

  const submit = (letter: OptionLetter) => {
    if (!interactive || answered || busy || !onSubmit) return;
    onSubmit(letter);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const key = e.key.toLowerCase();
    if (canPick && ["a", "b", "c", "d"].includes(key)) {
      e.preventDefault();
      setSelected(key.toUpperCase() as OptionLetter);
      return;
    }
    if (canPick && ["1", "2", "3", "4"].includes(key)) {
      e.preventDefault();
      setSelected(LETTERS[Number(key) - 1]);
      return;
    }
    if (e.key === "Enter" && interactive && !answered && !busy) {
      // Enter submits once something is selected (§14.3); with no selection,
      // let the focused option button's native activation select it first.
      if (selected) {
        e.preventDefault();
        submit(selected);
      }
    }
  };

  return (
    <div
      ref={cardRef}
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      aria-labelledby={`q-${question.question_id}-text`}
      className="rounded-2xl border border-border bg-surface p-4 shadow-sm outline-none focus-visible:outline-2 md:p-5"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-bold text-brand">
          Question {number} of {total}
        </span>
        <DifficultyBadge difficulty={question.difficulty} />
        {answered && (
          <span className="rounded-full border border-green-200 bg-green-50 px-2.5 py-0.5 text-xs font-semibold text-green-800">
            Answered
          </span>
        )}
      </div>

      <h3
        id={`q-${question.question_id}-text`}
        className="mt-3 text-base font-semibold leading-6 text-slate-900 md:text-lg"
      >
        {question.text}
      </h3>

      <div className="mt-4 flex flex-col gap-2" role="group" aria-label="Answer options">
        {LETTERS.map((letter) => {
          const text = question.options[letter];
          const isSelected = selected === letter;
          const isAnsweredChoice = answered && answeredText === text;
          const disabled = !canPick;

          let cls =
            "w-full rounded-xl border px-3 py-2.5 text-left text-sm transition-colors disabled:cursor-not-allowed ";
          if (isAnsweredChoice || (isSelected && !answered)) {
            cls += "border-brand bg-indigo-50 text-slate-900 ring-2 ring-brand/25 ";
          } else {
            cls +=
              "border-border bg-background text-slate-800 hover:border-brand/50 hover:bg-indigo-50/40 disabled:opacity-70 disabled:hover:border-border disabled:hover:bg-background ";
          }

          return (
            <button
              key={letter}
              type="button"
              disabled={disabled}
              aria-pressed={isSelected || isAnsweredChoice}
              onClick={() => {
                setSelected(letter);
              }}
              className={`flex min-h-11 items-center gap-3 ${cls}`}
            >
              <span
                aria-hidden="true"
                className={`flex size-7 shrink-0 items-center justify-center rounded-lg border text-xs font-bold ${
                  isAnsweredChoice || (isSelected && !answered)
                    ? "border-brand bg-brand text-white"
                    : "border-border bg-surface text-muted"
                }`}
              >
                {letter}
              </span>
              <span className="min-w-0 flex-1">{text}</span>
            </button>
          );
        })}
      </div>

      {interactive && !answered && (
        <div className="mt-4 flex flex-col gap-3">
          <button
            type="button"
            disabled={!selected || busy}
            onClick={() => selected && submit(selected)}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-brand px-6 text-sm font-semibold text-white transition-colors hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
            {busy ? "Checking…" : "Submit answer"}
          </button>
          <p className="text-xs text-muted">There are 3 questions — no going back.</p>
        </div>
      )}

      {!interactive && !answered && (
        <p className="mt-3 text-xs text-muted">There are 3 questions — no going back.</p>
      )}
    </div>
  );
}
