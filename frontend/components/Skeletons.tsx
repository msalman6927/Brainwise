/** Shimmer skeletons for auth hydration, dashboard list, and chat hydration (§8, §14). */

export function FullPageSkeleton() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-6">
      <div className="bw-skeleton h-8 w-36 rounded-full" aria-hidden="true" />
      <div className="bw-skeleton h-4 w-64 rounded-full" aria-hidden="true" />
      <div className="bw-skeleton h-4 w-48 rounded-full" aria-hidden="true" />
      <span className="mt-2 text-sm text-muted">Loading Brainwise…</span>
    </div>
  );
}

export function ThreadSkeletons({ count = 3 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-3" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-2xl border border-border bg-surface p-4">
          <div className="bw-skeleton h-4 w-2/3 rounded-full" />
          <div className="mt-3 flex gap-2">
            <div className="bw-skeleton h-5 w-20 rounded-full" />
            <div className="bw-skeleton h-5 w-14 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ChatSkeleton() {
  return (
    <div className="flex flex-col gap-5 p-4 md:p-6" aria-hidden="true">
      <div className="bw-skeleton h-12 w-1/2 self-end rounded-2xl" />
      <div className="bw-skeleton h-24 w-3/4 rounded-2xl" />
      <div className="bw-skeleton h-12 w-1/3 self-end rounded-2xl" />
      <div className="bw-skeleton h-40 w-4/5 rounded-2xl" />
    </div>
  );
}
