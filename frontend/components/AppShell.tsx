"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { GraduationCap, LogOut, Menu, X } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { HealthDot } from "./HealthDot";
import { OfflineBanner } from "./OfflineBanner";

interface AppShellProps {
  /** Page-specific content for the sticky header (title, progress, actions). */
  header?: ReactNode;
  /** Rendered in the sidebar above the thread list (filter box / new-topic form). */
  sidebarTop?: ReactNode;
  /** The thread list itself (page decides filtering + empty states). */
  sidebarList?: ReactNode;
  children: ReactNode;
}

/** Shared app chrome: 280px desktop sidebar / mobile slide-over drawer, sticky header,
 *  offline banner, user chip + log out (§14 layout, §8.4 header). */
export function AppShell({ header, sidebarTop, sidebarList, children }: AppShellProps) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Close the drawer on navigation (state adjusted during render — React docs pattern).
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    setDrawerOpen(false);
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const sidebarBody = (
    <>
      <div className="hidden items-center gap-2 px-4 pt-4 pb-2 md:flex">
        <span className="flex size-8 items-center justify-center rounded-xl bg-brand text-white">
          <GraduationCap className="size-5" aria-hidden="true" />
        </span>
        <span className="text-lg font-bold tracking-tight text-slate-900">Brainwise</span>
      </div>
      {sidebarTop && <div className="px-4 pt-4 md:pt-2">{sidebarTop}</div>}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">{sidebarList}</div>
    </>
  );

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <OfflineBanner />

      <div className="flex min-h-0 flex-1">
        {/* Desktop sidebar (§14: fixed 280px). */}
        <aside className="hidden w-72 shrink-0 flex-col border-r border-border bg-surface md:flex">
          {sidebarBody}
        </aside>

        {/* Mobile drawer. */}
        {drawerOpen && (
          <div
            className="fixed inset-0 z-40 bg-slate-900/40 md:hidden"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
        )}
        <aside
          id="app-sidebar"
          className={`fixed inset-y-0 left-0 z-40 flex w-72 max-w-[85vw] flex-col border-r border-border bg-surface transition-transform duration-200 md:hidden ${
            drawerOpen ? "translate-x-0" : "-translate-x-full"
          }`}
          aria-hidden={!drawerOpen}
          inert={!drawerOpen}
        >
          <div className="flex items-center justify-between px-4 pt-4">
            <span className="flex items-center gap-2">
              <span className="flex size-8 items-center justify-center rounded-xl bg-brand text-white">
                <GraduationCap className="size-5" aria-hidden="true" />
              </span>
              <span className="text-lg font-bold tracking-tight text-slate-900">Brainwise</span>
            </span>
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              aria-label="Close menu"
              className="rounded-md p-2 text-muted hover:text-slate-900 bw-compact"
            >
              <X className="size-5" aria-hidden="true" />
            </button>
          </div>
          {sidebarBody}
        </aside>

        {/* Main column. */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header
            className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-surface px-3 md:px-4"
          >
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open menu"
              aria-expanded={drawerOpen}
              aria-controls="app-sidebar"
              className="rounded-md p-2 text-slate-700 hover:bg-background md:hidden bw-compact"
            >
              <Menu className="size-5" aria-hidden="true" />
            </button>

            <span className="flex items-center gap-2 md:hidden">
              <span className="flex size-7 items-center justify-center rounded-lg bg-brand text-white">
                <GraduationCap className="size-4" aria-hidden="true" />
              </span>
            </span>

            <div className="flex min-w-0 flex-1 items-center gap-2">{header}</div>

            <HealthDot />

            <div className="flex items-center gap-2">
              <span className="hidden items-center gap-2 rounded-full border border-border bg-background px-2.5 py-1 sm:flex">
                <span
                  aria-hidden="true"
                  className="flex size-6 items-center justify-center rounded-full bg-brand text-xs font-bold text-white"
                >
                  {(user?.name ?? "?").charAt(0).toUpperCase()}
                </span>
                <span className="max-w-32 truncate text-sm font-medium text-slate-800">
                  {user?.name}
                </span>
              </span>
              <button
                type="button"
                onClick={logout}
                aria-label="Log out"
                title="Log out"
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors hover:border-danger/40 hover:text-danger bw-compact"
              >
                <LogOut className="size-4" aria-hidden="true" />
                <span className="hidden lg:inline">Log out</span>
              </button>
            </div>
          </header>

          <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
        </div>
      </div>
    </div>
  );
}
