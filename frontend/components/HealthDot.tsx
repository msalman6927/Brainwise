"use client";

import { useStore } from "@/lib/store";

/** Green/grey status dot; click re-runs GET /health (§8 global, §7). */
export function HealthDot() {
  const { backendOnline, checkHealth } = useStore();
  const label =
    backendOnline === null
      ? "Checking server status…"
      : backendOnline
        ? "Server online"
        : "Server offline";

  return (
    <button
      type="button"
      onClick={() => void checkHealth()}
      aria-label={`${label}. Click to re-check`}
      title={label}
      className="flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-medium text-muted transition-colors hover:bg-background bw-compact"
    >
      <span
        aria-hidden="true"
        className={`size-2 rounded-full ${
          backendOnline === null
            ? "bg-slate-300"
            : backendOnline
              ? "bg-success"
              : "bg-slate-400"
        }`}
      />
      <span className="hidden sm:inline">{backendOnline === false ? "Offline" : "Server"}</span>
    </button>
  );
}
