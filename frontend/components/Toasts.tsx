"use client";

import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { useStore } from "@/lib/store";

const STYLES = {
  success: "border-success/30 bg-green-50 text-green-900",
  error: "border-danger/30 bg-red-50 text-red-900",
  info: "border-border bg-surface text-slate-800",
} as const;

const ICONS = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
} as const;

/** Global toasts — success/error, top-right, auto-dismiss 4s (§8.6). */
export function Toasts() {
  const { toasts, dismissToast } = useStore();

  return (
    <div
      className="fixed right-4 top-4 z-[60] flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2"
      aria-live="polite"
    >
      {toasts.map((t) => {
        const Icon = ICONS[t.kind];
        return (
          <div
            key={t.id}
            role="status"
            className={`bw-toast flex items-start gap-2 rounded-2xl border px-3 py-2.5 text-sm shadow-lg ${STYLES[t.kind]}`}
          >
            <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span className="flex-1">{t.message}</span>
            <button
              type="button"
              onClick={() => dismissToast(t.id)}
              aria-label="Dismiss notification"
              className="rounded-md p-1 opacity-60 transition-opacity hover:opacity-100 bw-compact"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
