"use client";

import { AlertTriangle, RotateCcw, X, ExternalLink } from "lucide-react";
import Link from "next/link";
import type { ErrorCode } from "@/lib/types";

export interface StreamErrorShape {
  code: ErrorCode;
  message: string;
  retryable: boolean;
}

interface ErrorCardProps {
  error: StreamErrorShape;
  onRetry: () => void;
  onDismiss: () => void;
  onReload?: () => void;
}

/** In-thread error card (§7, §8.5, §11): message + Retry when retryable,
 *  special copy for `unsupported_topic`, "Reload thread" for `invalid_phase`. */
export function ErrorCard({ error, onRetry, onDismiss, onReload }: ErrorCardProps) {
  const isUnsupported = error.code === "unsupported_topic";
  const isInvalidPhase = error.code === "invalid_phase";

  const message = isUnsupported
    ? "Brainwise can't quiz this topic yet — try rephrasing it."
    : error.message;

  const showRetry = error.retryable || error.code === "internal";
  const showDashboardLink = isUnsupported;

  return (
    <div
      role="alert"
      className="rounded-2xl border border-danger/40 bg-red-50 p-4 text-sm text-red-900"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">Something went wrong</p>
          <p className="mt-1 leading-6">{message}</p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {isInvalidPhase && onReload && (
              <button
                type="button"
                onClick={onReload}
                className="inline-flex items-center gap-1.5 rounded-full bg-brand px-4 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand-dark bw-compact"
              >
                <RotateCcw className="size-3.5" aria-hidden="true" />
                Reload thread
              </button>
            )}
            {!isInvalidPhase && showRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 rounded-full bg-danger px-4 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-red-700 bw-compact"
              >
                <RotateCcw className="size-3.5" aria-hidden="true" />
                Retry
              </button>
            )}
            {showDashboardLink && (
              <Link
                href="/"
                className="inline-flex items-center gap-1.5 rounded-full border border-red-300 bg-white px-4 py-1.5 text-xs font-semibold text-red-800 transition-colors hover:bg-red-100 bw-compact"
              >
                <ExternalLink className="size-3.5" aria-hidden="true" />
                Back to dashboard
              </Link>
            )}
            <button
              type="button"
              onClick={onDismiss}
              className="inline-flex items-center gap-1.5 rounded-full border border-red-300 bg-white px-4 py-1.5 text-xs font-semibold text-red-800 transition-colors hover:bg-red-100 bw-compact"
            >
              <X className="size-3.5" aria-hidden="true" />
              Dismiss
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
