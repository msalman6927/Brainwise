"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, GraduationCap, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useStore } from "@/lib/store";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function readNext(): string {
  if (typeof window === "undefined") return "/";
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") ? next : "/";
}

const subscribeNoop = () => () => {};

export default function LoginPage() {
  const router = useRouter();
  const { user, loading, login } = useAuth();
  const { checkHealth } = useStore();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const nextPath = useSyncExternalStore(subscribeNoop, readNext, () => "/");
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!loading && user) router.replace(readNext());
  }, [loading, user, router]);

  const valid = EMAIL_RE.test(email.trim()) && password.length > 0;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBanner(null);
    const nextErrors: typeof errors = {};
    if (!EMAIL_RE.test(email.trim())) nextErrors.email = "Enter a valid email address.";
    if (password.length === 0) nextErrors.password = "Enter your password.";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setSubmitting(true);
    try {
      await login(email.trim(), password);
      router.replace(readNext());
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "invalid_credentials" || err.status === 401) {
          setBanner("Invalid email or password. Try again or create an account.");
        } else if (err.code === "invalid_request") {
          const next: typeof errors = {};
          for (const f of err.fields) {
            if (f.loc.includes("email")) next.email = f.msg;
            if (f.loc.includes("password")) next.password = f.msg;
          }
          setErrors(next);
          setBanner(err.message);
        } else {
          setBanner(err.message || "Something went wrong. Try again.");
        }
        void checkHealth();
      } else {
        setBanner("Can't reach the server — is the backend running on port 8000?");
        void checkHealth();
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-10">
      <main className="w-full max-w-md rounded-2xl border border-border bg-surface p-6 shadow-sm md:p-8">
        <div className="flex flex-col items-center text-center">
          <span className="flex size-11 items-center justify-center rounded-2xl bg-brand text-white">
            <GraduationCap className="size-6" aria-hidden="true" />
          </span>
          <h1
            ref={headingRef}
            tabIndex={-1}
            className="mt-3 text-2xl font-bold tracking-tight text-slate-900 outline-none"
          >
            Brainwise
          </h1>
          <p className="mt-1 text-sm text-muted">Learn any topic, at your level.</p>
        </div>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4" noValidate>
          <div aria-live="polite">
            {banner && (
              <p className="rounded-xl border border-danger/30 bg-red-50 px-3 py-2.5 text-sm text-red-800">
                {banner}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-800">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@student.edu"
              autoComplete="email"
              disabled={submitting}
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? "email-error" : undefined}
              className="h-11 w-full rounded-xl border border-border bg-background px-3.5 text-sm text-slate-900 outline-none transition-colors placeholder:text-muted focus:border-brand"
            />
            {errors.email && (
              <p id="email-error" className="mt-1 text-xs font-medium text-danger">
                {errors.email}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-800">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                autoComplete="current-password"
                disabled={submitting}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? "password-error" : undefined}
                className="h-11 w-full rounded-xl border border-border bg-background px-3.5 pr-11 text-sm text-slate-900 outline-none transition-colors placeholder:text-muted focus:border-brand"
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                aria-label={showPw ? "Hide password" : "Show password"}
                className="absolute top-1/2 right-2 -translate-y-1/2 rounded-md p-2 text-muted transition-colors hover:text-slate-900 bw-compact"
              >
                {showPw ? (
                  <EyeOff className="size-4" aria-hidden="true" />
                ) : (
                  <Eye className="size-4" aria-hidden="true" />
                )}
              </button>
            </div>
            {errors.password && (
              <p id="password-error" className="mt-1 text-xs font-medium text-danger">
                {errors.password}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={!valid || submitting}
            className="mt-1 inline-flex h-11 items-center justify-center gap-2 rounded-full bg-brand px-6 text-sm font-semibold text-white transition-colors hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-5 flex flex-col items-center gap-2 text-sm">
          <Link href={`/register?next=${encodeURIComponent(nextPath)}`} className="font-medium text-brand hover:underline">
            New here? Create an account
          </Link>
          <Link href="/" className="text-muted hover:text-slate-900 hover:underline">
            Back to homepage
          </Link>
        </div>
      </main>
    </div>
  );
}
