"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Trash2 } from "lucide-react";
import { topicsApi } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { Topic } from "@/lib/types";
import { IqChip, LevelBadge, PhaseChip } from "./Chips";
import { ConfirmModal } from "./ConfirmModal";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

interface ThreadCardProps {
  thread: Topic;
  variant?: "sidebar" | "grid";
  onDeleted?: (id: string) => void;
}

export function ThreadCard({ thread, variant = "sidebar", onDeleted }: ThreadCardProps) {
  const { removeThread, pushToast } = useStore();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const handleDelete = async () => {
    setConfirmOpen(false);
    setLeaving(true);
    try {
      await topicsApi.remove(thread.id);
      removeThread(thread.id);
      pushToast("success", "Thread deleted");
      onDeleted?.(thread.id);
    } catch {
      setLeaving(false);
      pushToast("error", "Couldn't delete the thread — try again.");
    }
  };

  const isGrid = variant === "grid";

  return (
    <div
      className={`group relative rounded-2xl border border-border bg-surface shadow-sm transition-all duration-200 hover:border-brand/40 hover:shadow ${
        leaving ? "scale-95 opacity-0" : "scale-100 opacity-100"
      } ${isGrid ? "p-4" : "p-3"}`}
    >
      <Link
        href={`/chat/${thread.id}`}
        className="block rounded-md outline-none"
        aria-label={`Open topic ${thread.title}`}
      >
        <span className={`block truncate font-semibold text-slate-900 ${isGrid ? "text-base" : "text-sm"}`}>
          {thread.title}
        </span>
      </Link>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {thread.level && <LevelBadge level={thread.level} />}
        {thread.iq_score !== null && <IqChip iq={thread.iq_score} />}
        <PhaseChip phase={thread.phase} />
        <span className="ml-auto text-xs text-muted">{timeAgo(thread.updated_at)}</span>
      </div>

      {/* Hover / focus-within actions (§8.4). */}
      <div
        className={`mt-2 flex items-center gap-2 transition-opacity ${
          isGrid ? "opacity-100" : "opacity-0 focus-within:opacity-100 group-hover:opacity-100"
        }`}
      >
        <Link
          href={`/chat/${thread.id}`}
          className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-xs font-medium text-slate-700 transition-colors hover:border-brand/40 hover:text-brand bw-compact"
        >
          Open <ArrowRight className="size-3" aria-hidden="true" />
        </Link>
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          aria-label={`Delete "${thread.title}"`}
          className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-xs font-medium text-danger transition-colors hover:border-danger/40 hover:bg-red-50 bw-compact"
        >
          <Trash2 className="size-3" aria-hidden="true" />
          Delete
        </button>
      </div>

      <ConfirmModal
        open={confirmOpen}
        title={`Delete “${thread.title}”?`}
        body="This removes the thread from your list. It can't be undone."
        confirmLabel="Delete"
        onConfirm={() => void handleDelete()}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
