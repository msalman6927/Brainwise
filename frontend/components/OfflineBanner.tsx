"use client";

import { RefreshCw, WifiOff } from "lucide-react";
import { useStore } from "@/lib/store";

/** Top banner when the backend is unreachable + Retry re-running GET /health (§8.6). */
export function OfflineBanner() {
  const { backendOnline, checkHealth } = useStore();
  if (backendOnline !== false) return null;

  return (
    <div
      role="alert"
      className="flex shrink-0 flex-wrap items-center justify-center gap-3 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900"
    >
      <WifiOff className="size-4 shrink-0" aria-hidden="true" />
      <span>Can&apos;t reach the Brainwise server — is the backend running on port 8000?</span>
      <button
        type="button"
        onClick={() => void checkHealth()}
        className="inline-flex items-center gap-1.5 rounded-full border border-amber-400 bg-white px-3 py-1 font-medium text-amber-900 transition-colors hover:bg-amber-100 bw-compact"
      >
        <RefreshCw className="size-3.5" aria-hidden="true" />
        Retry
      </button>
    </div>
  );
}
