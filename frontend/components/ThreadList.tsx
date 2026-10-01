"use client";

import type { ReactNode } from "react";
import type { Topic } from "@/lib/types";
import { ThreadCard } from "./ThreadCard";

interface ThreadListProps {
  threads: Topic[];
  loading?: boolean;
  skeletons?: ReactNode;
  empty?: ReactNode;
  variant?: "sidebar" | "grid";
  onDeleted?: (id: string) => void;
}

/** Thread cards list with loading + empty slots (§8.4). */
export function ThreadList({
  threads,
  loading = false,
  skeletons,
  empty,
  variant = "sidebar",
  onDeleted,
}: ThreadListProps) {
  if (loading && skeletons) return <>{skeletons}</>;
  if (!loading && threads.length === 0 && empty) return <>{empty}</>;

  if (variant === "grid") {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {threads.map((t) => (
          <ThreadCard key={t.id} thread={t} variant="grid" onDeleted={onDeleted} />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {threads.map((t) => (
        <ThreadCard key={t.id} thread={t} variant="sidebar" onDeleted={onDeleted} />
      ))}
    </div>
  );
}
