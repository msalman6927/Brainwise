"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { ApiError, authApi, tokens } from "./api";
import type { User } from "./types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (b: { email: string; password: string; name: string }) => Promise<User>;
  logout: () => void;
  sessionExpired: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  // Boot hydration (§3): load tokens, then /auth/me (silent refresh on 401).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      tokens.load();
      if (tokens.access || tokens.refresh) {
        try {
          const me = await authApi.me();
          if (!cancelled) setUser(me);
        } catch {
          if (!cancelled) setUser(null);
        }
      }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const pair = await authApi.login({ email, password });
    tokens.access = pair.access;
    tokens.refresh = pair.refresh;
    setUser(await authApi.me());
  }, []);

  const register = useCallback(async (b: { email: string; password: string; name: string }) => {
    const res = await authApi.register(b);
    tokens.access = res.access;
    tokens.refresh = res.refresh;
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    authApi.logout();
    setUser(null);
    router.replace("/login");
  }, [router]);

  const sessionExpired = useCallback(() => {
    tokens.clear();
    setUser(null);
    router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [router, pathname]);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, sessionExpired }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Client-side gate for protected pages: skeleton while hydrating,
 *  redirect to /login?next= when there is no session (§13). */
export function useRequireAuth(): { user: User | null; ready: boolean; sessionExpired: () => void } {
  const { user, loading, sessionExpired } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, user, router, pathname]);

  return { user, ready: !loading && !!user, sessionExpired };
}

/** Map an unexpected API failure to the right recovery: 401 → login redirect. */
export function handleAuthError(e: unknown, sessionExpired: () => void): boolean {
  if (e instanceof ApiError && e.status === 401) {
    sessionExpired();
    return true;
  }
  return false;
}
