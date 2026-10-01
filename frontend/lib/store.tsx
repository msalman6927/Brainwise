"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { healthApi, topicsApi } from "./api";
import type { Topic } from "./types";

export type ToastKind = "success" | "error" | "info";
export interface Toast { id: number; kind: ToastKind; message: string }

interface StoreContextValue {
  threads: Topic[];
  threadsLoading: boolean;
  loadThreads: () => Promise<void>;
  upsertThread: (t: Topic) => void;
  removeThread: (id: string) => void;

  backendOnline: boolean | null; // null = still checking
  checkHealth: () => Promise<boolean>;

  toasts: Toast[];
  pushToast: (kind: ToastKind, message: string) => void;
  dismissToast: (id: number) => void;
}

const StoreContext = createContext<StoreContextValue | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [threads, setThreads] = useState<Topic[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(true);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);

  const pushToast = useCallback((kind: ToastKind, message: string) => {
    const id = ++toastId.current;
    setToasts((prev) => [...prev, { id, kind, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const loadThreads = useCallback(async () => {
    try {
      setThreads(await topicsApi.list());
    } catch {
      // keep whatever we had; offline banner covers connectivity problems
    } finally {
      setThreadsLoading(false);
    }
  }, []);

  const upsertThread = useCallback((t: Topic) => {
    setThreads((prev) => {
      const rest = prev.filter((x) => x.id !== t.id);
      return [t, ...rest];
    });
  }, []);

  const removeThread = useCallback((id: string) => {
    setThreads((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      await healthApi.check();
      setBackendOnline(true);
      return true;
    } catch {
      setBackendOnline(false);
      return false;
    }
  }, []);

  // Boot health probe (§7: GET /health on app boot).
  useEffect(() => {
    const id = setTimeout(() => {
      void checkHealth();
    }, 0);
    return () => clearTimeout(id);
  }, [checkHealth]);

  return (
    <StoreContext.Provider
      value={{
        threads,
        threadsLoading,
        loadThreads,
        upsertThread,
        removeThread,
        backendOnline,
        checkHealth,
        toasts,
        pushToast,
        dismissToast,
      }}
    >
      {children}
    </StoreContext.Provider>
  );
}

export function useStore(): StoreContextValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used within StoreProvider");
  return ctx;
}
