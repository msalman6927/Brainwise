"use client";

import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowDown, Loader2 } from "lucide-react";
import { Markdown } from "@/lib/markdown";
import type { ViewItem } from "@/lib/restore";
import type { OptionLetter, Phase, ScoreResult } from "@/lib/types";
import { McqCard } from "./McqCard";
import { ScoreReveal } from "./ScoreReveal";

interface MessageListProps {
  items: ViewItem[];
  score: ScoreResult | null;
  phase: Phase;
  streaming: boolean;
  streamText: string;
  /** Live `question_index` while the next question is being generated. */
  questionIndex: number | null;
  total: number;
  busy: boolean;
  focusSignal: number;
  onSubmitAnswer: (letter: OptionLetter) => void;
}

function UserBubble({ item }: { item: Extract<ViewItem, { kind: "user" }> }) {
  const { message } = item;
  if (message.phase === "assessing") {
    // Student answer chip: shows the picked option TEXT (§8.5).
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-full border border-brand/30 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-900">
          {message.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-sm leading-6 text-white">
        {message.content}
      </div>
    </div>
  );
}

/** Message list rendered by phase (§8.5) + live stream layers, with throttled
 *  aria-live announcements, auto-scroll and a "Jump to latest" pill (§14). */
export function MessageList({
  items,
  score,
  phase,
  streaming,
  streamText,
  questionIndex,
  total,
  busy,
  focusSignal,
  onSubmitAnswer,
}: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const streamTextRef = useRef("");
  const [atBottom, setAtBottom] = useState(true);
  const [liveText, setLiveText] = useState("");

  // Auto-scroll with new content unless the student scrolled up (§14.6).
  useEffect(() => {
    const el = scrollRef.current;
    if (el && atBottom) el.scrollTop = el.scrollHeight;
  }, [items, streamText, score, phase, atBottom]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

  const jumpToLatest = () => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    setAtBottom(true);
  };

  // Throttled aria-live region for streamed text (§14 a11y).
  useEffect(() => {
    if (!streaming) {
      const t = setTimeout(() => setLiveText(""), 300);
      return () => clearTimeout(t);
    }
    const id = setInterval(() => {
      const t = streamTextRef.current;
      setLiveText(t ? t.slice(-160) : "Brainwise is responding…");
    }, 1200);
    return () => clearInterval(id);
  }, [streaming]);

  useEffect(() => {
    streamTextRef.current = streamText;
  }, [streamText]);

  const last = items[items.length - 1];
  const hasActiveQuestion = !!last && last.kind === "question";
  const firstExplainingIndex = score
    ? items.findIndex((i) => i.kind === "assistant-text" && i.message.phase === "explaining")
    : -1;
  const scorePlaced = firstExplainingIndex !== -1;

  const computedIndex =
    questionIndex ?? (items.filter((i) => i.kind === "question").length || 1);
  const generatingQuestion =
    streaming && phase === "assessing" && !hasActiveQuestion;

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={scrollRef} onScroll={onScroll} className="h-full overflow-y-auto" tabIndex={0}>
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 md:p-6">
          {items.length === 0 && !streaming && (
            <div className="rounded-2xl border border-dashed border-border bg-surface p-6 text-center text-sm text-muted">
              No messages yet — press Send to start your assessment.
            </div>
          )}

          {items.map((item, i) => {
            const next = items[i + 1];

            let node: ReactNode = null;
            if (item.kind === "user") {
              node = <UserBubble item={item} />;
            } else if (item.kind === "question") {
              const answered =
                next?.kind === "user" && next.message.phase === "assessing";
              const interactive =
                i === items.length - 1 && phase === "assessing" && !answered;
              node = (
                <McqCard
                  key={item.question.question_id}
                  question={item.question}
                  number={
                    items.slice(0, i + 1).filter((x) => x.kind === "question").length
                  }
                  total={total}
                  answeredText={answered && next.kind === "user" ? next.message.content : null}
                  interactive={interactive}
                  busy={busy}
                  onSubmit={onSubmitAnswer}
                  focusSignal={interactive ? focusSignal : 0}
                />
              );
            } else if (item.message.phase === "explaining") {
              node = (
                <article className="rounded-2xl border border-border bg-surface p-4 shadow-sm md:p-6">
                  <Markdown>{item.message.content}</Markdown>
                </article>
              );
            } else {
              node = (
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-border bg-surface px-4 py-3 shadow-sm">
                    <Markdown>{item.message.content}</Markdown>
                  </div>
                </div>
              );
            }

            return (
              <Fragment key={item.message.id}>
                {i === firstExplainingIndex && score && <ScoreReveal score={score} />}
                {node}
              </Fragment>
            );
          })}

          {/* Score from a live stream (not yet in items). */}
          {score && !scorePlaced && <ScoreReveal score={score} />}

          {/* Scoring spinner (§6: "Calculating your level…"). */}
          {phase === "scoring" && streaming && (
            <div className="flex items-center justify-center gap-2 rounded-2xl border border-border bg-surface p-4 text-sm font-medium text-muted">
              <Loader2 className="size-4 animate-spin text-brand" aria-hidden="true" />
              Calculating your level…
            </div>
          )}

          {/* Generating-question shimmer (§14). */}
          {generatingQuestion && (
            <div className="flex items-center gap-3 rounded-2xl border border-border bg-surface p-4 shadow-sm">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand/10">
                <Loader2 className="size-5 animate-spin text-brand" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900">
                  Brainwise is writing question {Math.min(computedIndex, total)}…
                </p>
                <div className="mt-2 flex gap-1.5" aria-hidden="true">
                  {[0, 1, 2].map((d) => (
                    <span
                      key={d}
                      className={`bw-skeleton h-1.5 w-10 rounded-full ${
                        d === (computedIndex - 1) % 3 ? "opacity-100" : "opacity-50"
                      }`}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Live streaming markdown bubble with cursor (§8.5, §14.5). */}
          {streamText.length > 0 && (
            <div className="flex justify-start">
              <div className="max-w-full rounded-2xl rounded-bl-md border border-border bg-surface px-4 py-3 shadow-sm md:px-5">
                <Markdown>{streamText}</Markdown>
                {streaming && <span className="bw-cursor" aria-hidden="true" />}
              </div>
            </div>
          )}

          <div aria-live="polite" className="sr-only">
            {liveText}
          </div>
        </div>
      </div>

      {!atBottom && (
        <button
          type="button"
          onClick={jumpToLatest}
          className="absolute right-4 bottom-4 inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-lg transition-colors hover:bg-background"
        >
          <ArrowDown className="size-3.5" aria-hidden="true" />
          Jump to latest
        </button>
      )}
    </div>
  );
}
