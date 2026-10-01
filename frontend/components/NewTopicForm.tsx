"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Sparkles } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useStore } from "@/lib/store";
import { streamChat } from "@/lib/streamChat";

interface NewTopicFormProps {
  variant?: "hero" | "compact";
  autoFocus?: boolean;
  onStarted?: (threadId: string) => void;
}

/** Dashboard / sidebar new-topic form (§8.4): one input → POST /chat {topic, message}
 *  → adopts thread_id from `question`/`done` → navigates to the thread. */
export function NewTopicForm({ variant = "hero", autoFocus = false, onStarted }: NewTopicFormProps) {
  const router = useRouter();
  const { sessionExpired } = useAuth();
  const { loadThreads, pushToast, checkHealth } = useStore();
  const [topic, setTopic] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isHero = variant === "hero";
  const trimmed = topic.trim();
  const canSubmit = trimmed.length > 0 && !starting;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setStarting(true);

    let newThreadId: string | null = null;
    let terminal = false;

    try {
      for await (const ev of streamChat({
        topic: trimmed,
        message: `I want to study ${trimmed}`.slice(0, 4000),
      })) {
        if (ev.event === "question") {
          newThreadId = ev.data.thread_id ?? newThreadId;
        } else if (ev.event === "done") {
          terminal = true;
          newThreadId = ev.data.thread_id;
        } else if (ev.event === "error") {
          terminal = true;
          setError(
            ev.data.code === "unsupported_topic"
              ? "Brainwise can't quiz this topic yet — try rephrasing it."
              : ev.data.message,
          );
        }
      }

      if (newThreadId && terminal) {
        await loadThreads();
        pushToast("success", "Topic started — here's your first question.");
        onStarted?.(newThreadId);
        router.push(`/chat/${newThreadId}`);
      } else if (!terminal) {
        setError("The connection dropped before the question was ready — try again.");
        void checkHealth();
      }
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 401) {
          sessionExpired();
          return;
        }
        if (e.code === "unsupported_topic") {
          setError("Brainwise can't quiz this topic yet — try rephrasing it.");
        } else if (e.code === "invalid_request") {
          const field = e.fields.find((f) => f.loc.includes("title") || f.loc.includes("topic"));
          setError(field?.msg ?? e.message);
        } else {
          setError(e.message);
        }
        void checkHealth();
      } else {
        setError("Can't reach the server — check that the backend is running on port 8000.");
        void checkHealth();
      }
    } finally {
      setStarting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className={isHero ? "w-full" : "w-full"} noValidate>
      <label htmlFor={isHero ? "topic-hero" : "topic-compact"} className="sr-only">
        Topic to study
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id={isHero ? "topic-hero" : "topic-compact"}
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="e.g. Photosynthesis, Trigonometry, HTTP caching…"
          maxLength={200}
          autoComplete="off"
          autoFocus={autoFocus}
          disabled={starting}
          className={`min-w-0 flex-1 rounded-full border border-border bg-surface px-4 text-sm text-slate-900 shadow-sm outline-none transition-colors placeholder:text-muted focus:border-brand ${
            isHero ? "h-12 text-base" : "h-10"
          }`}
        />
        <button
          type="submit"
          disabled={!canSubmit}
          className={`inline-flex shrink-0 items-center justify-center gap-2 rounded-full font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
            isHero ? "h-12 px-6" : "h-10 px-4"
          } ${starting ? "bg-brand" : "bg-brand hover:bg-brand-dark"}`}
        >
          {starting ? (
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles className="size-4" aria-hidden="true" />
          )}
          {starting ? "Preparing your first question…" : "Start learning"}
        </button>
      </div>

      {isHero && (
        <p className="mt-2 text-sm text-muted">
          Type the topic you want to study — Brainwise will ask 3 quick questions first.
        </p>
      )}

      <div aria-live="polite">
        {error && (
          <p className="mt-2 rounded-xl border border-danger/30 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </p>
        )}
      </div>
    </form>
  );
}
