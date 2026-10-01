"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, GraduationCap, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useStore } from "@/lib/store";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PW_RE = /^(?=.*[a-zA-Z])(?=.*\d).{8,72}$/;

function readNext(): string {
  if (typeof window === "undefined") return "/";
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") ? next : "/";
}

const subscribeNoop = () => () => {};

interface FormErrors {
  name?: string;
  email?: string;
  password?: string;
}

export default function RegisterPage() {
  const router = useRouter();
  const { user, loading, register } = useAuth();
  const { checkHealth, pushToast } = useStore();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const nextPath = useSyncExternalStore(subscribeNoop, readNext, () => "/");
  const [touched, setTouched] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!loading && user) router.replace(readNext());
  }, [loading, user, router]);

  const passwordOk = PW_RE.test(password);
  const emailOk = EMAIL_RE.test(email.trim());
  const nameOk = name.trim().length >= 1;
  const valid = nameOk && emailOk && passwordOk;

  const validate = (): FormErrors => {
    const next: FormErrors = {};
    if (!nameOk) next.name = "Enter your name.";
    if (!emailOk) next.email = "Enter a valid email address.";
    if (!passwordOk)
      next.password = "Use 8+ characters with at least one letter and one digit.";
    return next;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBanner(null);
    setTouched(true);
    const nextErrors = validate();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setSubmitting(true);
    try {
      const created = await register({
        email: email.trim(),
        password,
        name: name.trim(),
      });
      pushToast("success", `Welcome, ${created.name}!`);
      router.replace(readNext());
    } catch (err) {
      if (err instanceof ApiError) {
        const next: FormErrors = {};
        for (const f of err.fields) {
          if (f.loc.includes("email")) {
            next.email =
              f.msg.toLowerCase().includes("already")
                ? "Email already registered"
                : f.msg;
          }
          if (f.loc.includes("password")) next.password = f.msg;
          if (f.loc.includes("name")) next.name = f.msg;
        }
        setErrors(next);
        if (Object.keys(next).length === 0) setBanner(err.message);
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
            Create your account
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
            <label htmlFor="name" className="mb-1 block text-sm font-medium text-slate-800">
              Full name
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Ayesha Khan"
              maxLength={120}
              autoComplete="name"
              disabled={submitting}
              aria-invalid={!!errors.name}
              aria-describedby={errors.name ? "name-error" : undefined}
              className="h-11 w-full rounded-xl border border-border bg-background px-3.5 text-sm text-slate-900 outline-none transition-colors placeholder:text-muted focus:border-brand"
            />
            {errors.name && (
              <p id="name-error" className="mt-1 text-xs font-medium text-danger">
                {errors.name}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="reg-email" className="mb-1 block text-sm font-medium text-slate-800">
              Email
            </label>
            <input
              id="reg-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@student.edu"
              autoComplete="email"
              disabled={submitting}
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? "reg-email-error" : undefined}
              className="h-11 w-full rounded-xl border border-border bg-background px-3.5 text-sm text-slate-900 outline-none transition-colors placeholder:text-muted focus:border-brand"
            />
            {errors.email && (
              <p id="reg-email-error" className="mt-1 text-xs font-medium text-danger">
                {errors.email}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="reg-password" className="mb-1 block text-sm font-medium text-slate-800">
              Password
            </label>
            <div className="relative">
              <input
                id="reg-password"
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                autoComplete="new-password"
                disabled={submitting}
                aria-invalid={!!errors.password}
                aria-describedby={
                  errors.password ? "reg-password-error" : "reg-password-hint"
                }
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
            {!errors.password && (
              <p
                id="reg-password-hint"
                className={`mt-1 text-xs ${
                  password.length === 0
                    ? "text-muted"
                    : passwordOk
                      ? "text-success"
                      : "text-warning"
                }`}
              >
                Use 8+ characters with at least one letter and one digit
              </p>
            )}
            {errors.password && (
              <p id="reg-password-error" className="mt-1 text-xs font-medium text-danger">
                {errors.password}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={submitting || (touched && !valid)}
            className="mt-1 inline-flex h-11 items-center justify-center gap-2 rounded-full bg-brand px-6 text-sm font-semibold text-white transition-colors hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
            {submitting ? "Creating your account…" : "Create account"}
          </button>
        </form>

        <div className="mt-5 flex flex-col items-center gap-2 text-sm">
          <Link href={`/login?next=${encodeURIComponent(nextPath)}`} className="font-medium text-brand hover:underline">
            Already have an account? Sign in
          </Link>
        </div>
      </main>
    </div>
  );
}
