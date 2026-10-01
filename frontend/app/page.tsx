"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, Search, X } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { NewTopicForm } from "@/components/NewTopicForm";
import { FullPageSkeleton, ThreadSkeletons } from "@/components/Skeletons";
import { ThreadList } from "@/components/ThreadList";
import { useRequireAuth } from "@/lib/auth";
import { useStore } from "@/lib/store";

function FilterBox({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="relative">
      <label htmlFor="filter-topics" className="sr-only">
        Filter your topics
      </label>
      <Search
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
        aria-hidden="true"
      />
      <input
        id="filter-topics"
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Filter your topics…"
        className="h-10 w-full rounded-full border border-border bg-background pr-9 pl-9 text-sm text-slate-900 outline-none transition-colors placeholder:text-muted focus:border-brand"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear filter"
          className="absolute top-1/2 right-2 -translate-y-1/2 rounded-md p-1 text-muted hover:text-slate-900 bw-compact"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

function NoResults({ query, onClear }: { query: string; onClear: () => void }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-surface p-6 text-center">
      <p className="text-sm text-slate-800">No topics match “{query}”</p>
      <button
        type="button"
        onClick={onClear}
        className="mt-3 rounded-full border border-border bg-background px-4 py-1.5 text-sm font-medium text-slate-700 transition-colors hover:border-brand/40 hover:text-brand bw-compact"
      >
        Clear filter
      </button>
    </div>
  );
}

export default function DashboardPage() {
  const { ready } = useRequireAuth();
  const { threads, threadsLoading, loadThreads } = useStore();
  const [query, setQuery] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (ready) void loadThreads();
  }, [ready, loadThreads]);

  useEffect(() => {
    if (ready) headingRef.current?.focus();
  }, [ready]);

  if (!ready) return <FullPageSkeleton />;

  const q = query.trim().toLowerCase();
  const filtered = q
    ? threads.filter((t) => t.title.toLowerCase().includes(q))
    : threads;
  const hasTopics = threads.length > 0;
  const noMatches = hasTopics && filtered.length === 0;

  const sidebarList = threadsLoading ? (
    <ThreadSkeletons count={3} />
  ) : noMatches ? (
    <NoResults query={query.trim()} onClear={() => setQuery("")} />
  ) : (
    <ThreadList
      threads={filtered}
      empty={
        <p className="rounded-xl border border-dashed border-border p-4 text-center text-sm text-muted">
          {hasTopics ? "No topics match your filter." : "No topics yet — what do you want to learn today?"}
        </p>
      }
    />
  );

  return (
    <AppShell
      sidebarTop={
        <div className="flex flex-col gap-3">
          <NewTopicForm variant="compact" />
          <FilterBox value={query} onChange={setQuery} />
        </div>
      }
      sidebarList={sidebarList}
    >
      <div className="h-full overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-8 md:py-12">
          <h1
            ref={headingRef}
            tabIndex={-1}
            className="text-2xl font-bold tracking-tight text-slate-900 outline-none md:text-3xl"
          >
            What do you want to learn today?
          </h1>

          <div className="mt-5">
            <NewTopicForm variant="hero" autoFocus={!hasTopics} />
          </div>

          {!threadsLoading && !hasTopics && (
            <div className="mt-10 flex flex-col items-center rounded-2xl border border-dashed border-border bg-surface px-6 py-10 text-center">
              <span className="flex size-14 items-center justify-center rounded-2xl bg-brand/10 text-brand">
                <BookOpen className="size-7" aria-hidden="true" />
              </span>
              <p className="mt-4 text-base font-medium text-slate-800">
                No topics yet — what do you want to learn today?
              </p>
              <p className="mt-1 text-sm text-muted">
                Pick anything you&apos;re studying — Brainwise will meet you at your level.
              </p>
            </div>
          )}

          {/* Mobile: the card grid lives in the main column (sidebar is a drawer). */}
          <div className="mt-6 md:hidden">
            {threadsLoading ? (
              <ThreadSkeletons count={3} />
            ) : noMatches ? (
              <NoResults query={query.trim()} onClear={() => setQuery("")} />
            ) : hasTopics ? (
              <ThreadList threads={filtered} variant="grid" />
            ) : null}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
