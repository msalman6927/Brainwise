"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowLeft, Trash2 } from "lucide-react";
import { IqChip, LevelBadge, PhaseChip } from "@/components/Chips";
import type { Phase, ScoreResult } from "@/lib/types";

interface ChatHeaderProps {
  title: string;
  phase: Phase;
  score: ScoreResult | null;
  questionIndex: number | null;
  total: number;
  onDelete: () => void;
}

/** Conversation header: back, title, phase chip, Question n of 3 dots (assessing),
 *  level + IQ chips (after score), delete (§8.5). */
export function ChatHeader({ title, phase, score, questionIndex, total, onDelete }: ChatHeaderProps) {
  const showProgress = phase === "assessing" && questionIndex !== null;
  const titleRef = useRef<HTMLSpanElement>(null);

  // Focus management on route change (§8.6): focus the thread title.
  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  return (
    <>
      <Link
        href="/"
        aria-label="Back to dashboard"
        className="rounded-md p-2 text-slate-700 transition-colors hover:bg-background bw-compact"
      >
        <ArrowLeft className="size-5" aria-hidden="true" />
      </Link>

      <div className="flex min-w-0 flex-col justify-center">
        <span
          ref={titleRef}
          tabIndex={-1}
          className="truncate text-sm font-semibold text-slate-900 outline-none"
          title={title}
        >
          {title || "Untitled topic"}
        </span>
        <div className="flex items-center gap-2" aria-live="polite">
          <PhaseChip phase={phase} />
          {showProgress && (
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted">
              Question {questionIndex} of {total}
              <span className="flex items-center gap-1" aria-hidden="true">
                {Array.from({ length: total }, (_, i) => (
                  <span
                    key={i}
                    className={`size-1.5 rounded-full transition-colors ${
                      i + 1 < questionIndex
                        ? "bg-brand"
                        : i + 1 === questionIndex
                          ? "bg-brand/60 ring-2 ring-brand/25"
                          : "bg-slate-300"
                    }`}
                  />
                ))}
              </span>
            </span>
          )}
        </div>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {score && <LevelBadge level={score.level} />}
        {score && <IqChip iq={score.iq_score} />}
        <button
          type="button"
          onClick={onDelete}
          aria-label="Delete thread"
          title="Delete thread"
          className="rounded-md p-2 text-muted transition-colors hover:bg-red-50 hover:text-danger bw-compact"
        >
          <Trash2 className="size-4" aria-hidden="true" />
        </button>
      </div>
    </>
  );
}
