"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ConfirmModal } from "@/components/ConfirmModal";
import { ChatSkeleton, FullPageSkeleton, ThreadSkeletons } from "@/components/Skeletons";
import { ThreadList } from "@/components/ThreadList";
import { NewTopicForm } from "@/components/NewTopicForm";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { Composer } from "@/components/chat/Composer";
import { ErrorCard, type StreamErrorShape } from "@/components/chat/ErrorCard";
import { MessageList } from "@/components/chat/MessageList";
import { SuggestionChips } from "@/components/chat/SuggestionChips";
import { ApiError, topicsApi } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { FALLBACK_SUGGESTIONS, extractSuggestions } from "@/lib/markdown";
import { pendingAnswer, toViewItems, type ViewItem } from "@/lib/restore";
import { useStore } from "@/lib/store";
import { streamChat } from "@/lib/streamChat";
import type {
  ChatRequest,
  OptionLetter,
  Phase,
  ScoreResult,
  Topic,
} from "@/lib/types";

const TOTAL_QUESTIONS = 3;

let liveId = 0;
const nextLiveId = (prefix: string) => `${prefix}-${Date.now()}-${++liveId}`;

/** All conversation state lives here, remounted per thread via `key` so
 *  navigating between threads resets cleanly (no stale items / in-flight stream). */
function ThreadView({ threadId }: { threadId: string }) {
  const router = useRouter();
  const { sessionExpired } = useRequireAuth();
  const { threads, threadsLoading, loadThreads, removeThread, pushToast, checkHealth } =
    useStore();

  const [hydrating, setHydrating] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [topic, setTopic] = useState<Topic | null>(null);
  const [items, setItems] = useState<ViewItem[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [questionIndex, setQuestionIndex] = useState<number | null>(null);
  const [score, setScore] = useState<ScoreResult | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamError, setStreamError] = useState<StreamErrorShape | null>(null);
  const [focusSignal, setFocusSignal] = useState(0);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const acRef = useRef<AbortController | null>(null);
  const lastRequestRef = useRef<ChatRequest | null>(null);
  const itemsRef = useRef<ViewItem[]>([]);
  const phaseRef = useRef<Phase>("idle");
  const streamTextRef = useRef("");
  const messagePhaseRef = useRef<Phase>("explaining");
  const hydratedRef = useRef<string | null>(null);
  const dismissedRef = useRef(false);
  const applyHistoryRef = useRef<(autoResume: boolean) => Promise<void>>(
    async () => {},
  );

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);
  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  // Abort the in-flight stream when leaving this thread (§5.5 resumable state).
  useEffect(() => {
    dismissedRef.current = false;
    return () => {
      dismissedRef.current = true;
      acRef.current?.abort();
      acRef.current = null;
    };
  }, []);

  // ---- local finalization of a streamed assistant message --------------------
  const finalizeIntoItems = useCallback(() => {
    const text = streamTextRef.current;
    if (text) {
      const messagePhase = messagePhaseRef.current;
      setItems((prev) => [
        ...prev,
        {
          kind: "assistant-text",
          message: {
            id: nextLiveId("live-a"),
            role: "assistant",
            content: text,
            phase: messagePhase,
            created_at: new Date().toISOString(),
          },
        },
      ]);
    }
    streamTextRef.current = "";
    setStreamText("");
  }, []);

  // ---- the single in-flight SSE consumer (§7 wiring) -------------------------
  const runStream = useCallback(
    async (request: ChatRequest): Promise<boolean> => {
      if (acRef.current) return false; // exactly one request per thread
      const ac = new AbortController();
      acRef.current = ac;
      lastRequestRef.current = request;
      streamTextRef.current = "";
      setStreamText("");
      setStreaming(true);
      setStreamError(null);
      messagePhaseRef.current = phaseRef.current === "follow_up" ? "follow_up" : "explaining";

      let sawTerminal = false;
      let receivedAnyFrame = false;
      let navigated = false;
      let reloadAfter = false;
      let persisted = false;

      try {
        for await (const ev of streamChat(request, ac.signal)) {
          receivedAnyFrame = true;
          persisted = true;

          switch (ev.event) {
            case "phase": {
              setPhase(ev.data.phase);
              phaseRef.current = ev.data.phase;
              setQuestionIndex(ev.data.question_index ?? null);
              break;
            }
            case "question": {
              const q = ev.data;
              setItems((prev) => [
                ...prev,
                {
                  kind: "question",
                  message: {
                    id: nextLiveId("live-q"),
                    role: "assistant",
                    content: JSON.stringify(q),
                    phase: "assessing",
                    created_at: new Date().toISOString(),
                  },
                  question: q,
                  answered: false,
                },
              ]);
              setQuestionIndex(null);
              setPhase("assessing");
              phaseRef.current = "assessing";
              setFocusSignal((s) => s + 1);
              break;
            }
            case "score": {
              const s = ev.data;
              setScore(s);
              setTopic((t) => (t ? { ...t, iq_score: s.iq_score, level: s.level } : t));
              break;
            }
            case "token": {
              streamTextRef.current += ev.data.delta;
              setStreamText(streamTextRef.current);
              messagePhaseRef.current =
                phaseRef.current === "follow_up" ? "follow_up" : "explaining";
              break;
            }
            case "done": {
              sawTerminal = true;
              const d = ev.data;
              if (d.thread_id !== threadId) {
                // follow-up agent started a NEW topic (§12.6) → navigate to it
                navigated = true;
                router.push(`/chat/${d.thread_id}`);
                break;
              }
              finalizeIntoItems();
              setPhase(d.phase);
              phaseRef.current = d.phase;
              setQuestionIndex(null);
              break;
            }
            case "error": {
              sawTerminal = true;
              setStreamError({
                code: ev.data.code,
                message: ev.data.message,
                retryable: ev.data.retryable,
              });
              break;
            }
          }
        }
        if (navigated) return true;
        if (!sawTerminal) {
          // Terminal invariant broken → connection died (§12.7): retryable.
          setStreamError({
            code: "internal",
            message: "The connection dropped — your thread is safe. Try again.",
            retryable: true,
          });
          void checkHealth();
          persisted = receivedAnyFrame;
        }
      } catch (e) {
        if ((e as Error)?.name === "AbortError") {
          finalizeIntoItems();
          if (!dismissedRef.current) pushToast("info", "Stopped.");
          if (phaseRef.current === "assessing") reloadAfter = true;
          persisted = true;
        } else if (e instanceof ApiError) {
          if (e.status === 401) {
            sessionExpired();
            return false;
          }
          if (e.code === "not_found") {
            setNotFound(true);
            return false;
          }
          if (e.code === "already_answered") {
            // §11: re-fetch history and re-render the latest state.
            reloadAfter = true;
            persisted = false;
          } else {
            // pre-stream HTTP envelope (§11)
            setStreamError({
              code: e.code as StreamErrorShape["code"],
              message: e.message,
              retryable: e.retryable,
            });
            return false;
          }
        } else {
          // network / CORS / backend down
          setStreamError({
            code: "internal",
            message: "Can't reach the server — the reply may not have finished.",
            retryable: true,
          });
          void checkHealth();
          persisted = receivedAnyFrame;
        }
      } finally {
        if (acRef.current === ac) acRef.current = null;
        setStreaming(false);
        void loadThreads(); // refresh sidebar badges (§7 done row)
      }

      if (reloadAfter) await applyHistoryRef.current(true);
      return persisted;
    },
    [threadId, finalizeIntoItems, router, loadThreads, pushToast, checkHealth, sessionExpired],
  );

  // ---- hydrate / reload history (§10.3 open-thread algorithm) ----------------
  const applyHistory = useCallback(
    async (autoResume: boolean) => {
      try {
        const [msgs, list] = await Promise.all([
          topicsApi.messages(threadId),
          topicsApi.list(),
        ]);
        const tp = list.find((t) => t.id === threadId) ?? null;
        setTopic(tp);
        setItems(toViewItems(msgs));
        setHydrating(false);
        setNotFound(false);

        const ph: Phase = tp?.phase ?? "idle";
        setPhase(ph);
        phaseRef.current = ph;
        if (tp?.iq_score != null && tp.level) {
          setScore({ iq_score: tp.iq_score, level: tp.level });
        }

        if (!autoResume || acRef.current) return;
        const pending = pendingAnswer(msgs);
        if (ph === "assessing" && pending) {
          await runStream({
            thread_id: threadId,
            question_id: pending.question_id,
            option: pending.option,
          });
        } else if (ph === "scoring" || ph === "explaining") {
          // dropped explanation stream → regenerate (§5.5, message not persisted)
          await runStream({ thread_id: threadId, message: "continue" });
        }
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.status === 404) setNotFound(true);
          else if (e.status === 401) sessionExpired();
          else
            setStreamError({
              code: e.code as StreamErrorShape["code"],
              message: e.message,
              retryable: e.retryable,
            });
        } else {
          setStreamError({
            code: "internal",
            message: "Can't reach the server — is the backend running on port 8000?",
            retryable: true,
          });
          void checkHealth();
        }
        setHydrating(false);
      }
    },
    [threadId, runStream, sessionExpired, checkHealth],
  );

  useEffect(() => {
    applyHistoryRef.current = applyHistory;
  }, [applyHistory]);

  // Initial hydration (hydratedRef also guards StrictMode's double mount).
  useEffect(() => {
    if (hydratedRef.current === threadId) return;
    hydratedRef.current = threadId;
    void applyHistory(true);
  }, [threadId, applyHistory]);

  // ---- user actions ----------------------------------------------------------
  const submitAnswer = useCallback(
    async (letter: OptionLetter) => {
      if (acRef.current) return;
      const last = itemsRef.current[itemsRef.current.length - 1];
      if (!last || last.kind !== "question") return;
      const q = last.question;
      const optionText = q.options[letter];

      const optimisticId = nextLiveId("live-u");
      setItems((prev) => [
        ...prev,
        {
          kind: "user",
          message: {
            id: optimisticId,
            role: "user",
            content: optionText,
            phase: "assessing",
            created_at: new Date().toISOString(),
          },
        },
      ]);

      const persisted = await runStream({
        thread_id: threadId,
        question_id: q.question_id,
        option: letter,
      });
      if (!persisted) {
        setItems((prev) => prev.filter((i) => i.message.id !== optimisticId));
      }
    },
    [runStream, threadId],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      if (acRef.current) return;
      if (phaseRef.current === "assessing" || phaseRef.current === "scoring") return;

      // Resume of a dropped explanation does NOT persist the message (§5.5).
      const willPersist = phaseRef.current !== "explaining";
      const optimisticId = nextLiveId("live-u");
      if (willPersist) {
        setItems((prev) => [
          ...prev,
          {
            kind: "user",
            message: {
              id: optimisticId,
              role: "user",
              content: text,
              phase: phaseRef.current,
              created_at: new Date().toISOString(),
            },
          },
        ]);
      }

      const persisted = await runStream({ thread_id: threadId, message: text });
      if (!persisted && willPersist) {
        setItems((prev) => prev.filter((i) => i.message.id !== optimisticId));
      }
    },
    [runStream, threadId],
  );

  const stopStream = useCallback(() => {
    acRef.current?.abort();
  }, []);

  const retryLast = useCallback(() => {
    const req = lastRequestRef.current;
    if (!req || acRef.current) return;
    setStreamError(null);
    void runStream(req);
  }, [runStream]);

  const handleDelete = useCallback(async () => {
    setDeleteOpen(false);
    try {
      await topicsApi.remove(threadId);
      removeThread(threadId);
      pushToast("success", "Thread deleted");
      router.push("/");
    } catch {
      pushToast("error", "Couldn't delete the thread — try again.");
    }
  }, [threadId, removeThread, pushToast, router]);

  // ---- derived ---------------------------------------------------------------
  const computedIndex = useMemo(
    () => items.filter((i) => i.kind === "question").length,
    [items],
  );
  const effectiveIndex =
    phase === "assessing" ? (questionIndex ?? (computedIndex || 1)) : null;

  const suggestions = useMemo(() => {
    if (phase !== "follow_up" || streaming || streamError) return [];
    const lastExplanation = [...items]
      .reverse()
      .find((i) => i.kind === "assistant-text" && i.message.phase === "explaining");
    const md =
      lastExplanation && lastExplanation.kind === "assistant-text"
        ? lastExplanation.message.content
        : "";
    const parsed = md ? extractSuggestions(md) : [];
    return parsed.length > 0 ? parsed : FALLBACK_SUGGESTIONS;
  }, [items, phase, streaming, streamError]);

  // ---- render ----------------------------------------------------------------
  const sidebarList = threadsLoading ? (
    <ThreadSkeletons count={3} />
  ) : (
    <ThreadList
      threads={threads}
      empty={
        <p className="rounded-xl border border-dashed border-border p-4 text-center text-sm text-muted">
          No topics yet — what do you want to learn today?
        </p>
      }
      onDeleted={(id) => {
        if (id === threadId) router.push("/");
      }}
    />
  );

  return (
    <AppShell
      header={
        <ChatHeader
          title={topic?.title ?? ""}
          phase={phase}
          score={score}
          questionIndex={effectiveIndex}
          total={TOTAL_QUESTIONS}
          onDelete={() => setDeleteOpen(true)}
        />
      }
      sidebarTop={<NewTopicForm variant="compact" />}
      sidebarList={sidebarList}
    >
      <div className="flex h-full flex-col">
        {hydrating ? (
          <div className="h-full overflow-y-auto">
            <ChatSkeleton />
          </div>
        ) : notFound ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
            <h1 className="text-lg font-semibold text-slate-900">
              This topic no longer exists
            </h1>
            <p className="text-sm text-muted">It may have been deleted.</p>
            <Link
              href="/"
              className="rounded-full bg-brand px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-dark"
            >
              Back to dashboard
            </Link>
          </div>
        ) : (
          <>
            <MessageList
              items={items}
              score={score}
              phase={phase}
              streaming={streaming}
              streamText={streamText}
              questionIndex={questionIndex}
              total={TOTAL_QUESTIONS}
              busy={streaming}
              focusSignal={focusSignal}
              onSubmitAnswer={(l) => void submitAnswer(l)}
            />

            <div aria-live="polite" className="sr-only">
              {phase}
            </div>

            {streamError && (
              <div className="px-4 pt-2 pb-1 md:px-6">
                <ErrorCard
                  error={streamError}
                  onRetry={retryLast}
                  onDismiss={() => setStreamError(null)}
                  onReload={() => void applyHistory(true)}
                />
              </div>
            )}

            <SuggestionChips
              suggestions={suggestions}
              onPick={(q) => void sendMessage(q)}
              disabled={streaming}
            />

            <Composer
              phase={phase}
              topicTitle={topic?.title ?? ""}
              streaming={streaming}
              onSend={(t) => void sendMessage(t)}
              onStop={stopStream}
            />
          </>
        )}
      </div>

      <ConfirmModal
        open={deleteOpen}
        title={`Delete “${topic?.title ?? "this thread"}”?`}
        body="This removes the thread from your list. It can't be undone."
        confirmLabel="Delete"
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteOpen(false)}
      />
    </AppShell>
  );
}

export default function ChatPage() {
  const { threadId } = useParams<{ threadId: string }>();
  const { ready } = useRequireAuth();

  if (!ready) return <FullPageSkeleton />;
  return <ThreadView key={threadId} threadId={threadId} />;
}
