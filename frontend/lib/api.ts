import type {
  ErrorEnvelope,
  Message,
  RegisterResponse,
  Topic,
  TokenPair,
  User,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const ACCESS_KEY = "brainwise.access";
const REFRESH_KEY = "brainwise.refresh";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryable = false,
    public details?: Record<string, unknown>,
  ) {
    super(message);
  }
  get fields(): { loc: string; msg: string }[] {
    const f = (this.details?.fields ?? []) as { loc: string; msg: string }[];
    return Array.isArray(f) ? f : [];
  }
}

const memory = { access: "" as string };
export const tokens = {
  get access() { return memory.access; },
  set access(v: string) { memory.access = v; if (typeof window !== "undefined") localStorage.setItem(ACCESS_KEY, v); },
  get refresh() { return typeof window === "undefined" ? "" : localStorage.getItem(REFRESH_KEY) ?? ""; },
  set refresh(v: string) { if (typeof window !== "undefined") localStorage.setItem(REFRESH_KEY, v); },
  load() { if (typeof window !== "undefined") memory.access = localStorage.getItem(ACCESS_KEY) ?? ""; },
  clear() {
    memory.access = "";
    if (typeof window !== "undefined") { localStorage.removeItem(ACCESS_KEY); localStorage.removeItem(REFRESH_KEY); }
  },
};

async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try { body = await res.json(); } catch { /* empty body (e.g. 204) */ }
  const env = body as ErrorEnvelope | null;
  return new ApiError(
    res.status,
    env?.error?.code ?? (res.status === 401 ? "unauthorized" : "internal"),
    env?.error?.message ?? `Request failed (${res.status})`,
    env?.error?.retryable ?? false,
    env?.error?.details,
  );
}

// single-flight refresh: concurrent 401s share one refresh call
let refreshing: Promise<string> | null = null;
async function refreshAccess(): Promise<string> {
  refreshing ??= (async () => {
    const refresh = tokens.refresh;
    if (!refresh) throw new ApiError(401, "unauthorized", "Not signed in");
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) { tokens.clear(); throw await toApiError(res); }
    const pair = (await res.json()) as TokenPair;
    tokens.access = pair.access;
    tokens.refresh = pair.refresh;
    return pair.access;
  })().finally(() => { refreshing = null; });
  return refreshing;
}

interface ApiOptions extends Omit<RequestInit, "headers"> {
  auth?: boolean;
  headers?: Record<string, string>;
}

export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { auth = true, ...init } = opts;
  const doFetch = (access: string) =>
    fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(auth && access ? { Authorization: `Bearer ${access}` } : {}),
        ...(init.headers ?? {}),
      },
      cache: "no-store",
    });

  let res = await doFetch(tokens.access);
  if (res.status === 401 && auth && !path.startsWith("/auth/") && tokens.refresh) {
    try {
      const access = await refreshAccess();
      res = await doFetch(access);
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw new ApiError(401, "unauthorized", "Session expired — please sign in");
    }
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const authApi = {
  register: (b: { email: string; password: string; name: string }) =>
    api<RegisterResponse>("/auth/register", { method: "POST", auth: false, body: JSON.stringify(b) }),
  login: (b: { email: string; password: string }) =>
    api<TokenPair>("/auth/login", { method: "POST", auth: false, body: JSON.stringify(b) }),
  me: () => api<User>("/auth/me"),
  logout: () => tokens.clear(),
};

export const topicsApi = {
  list: () => api<Topic[]>("/topics"),
  create: (title: string) =>
    api<Topic>("/topics", { method: "POST", body: JSON.stringify({ title }) }),
  messages: (id: string) => api<Message[]>(`/topics/${id}/messages`),
  remove: (id: string) => api<void>(`/topics/${id}`, { method: "DELETE" }),
};

export const healthApi = { check: () => api<{ status: string }>("/health", { auth: false }) };
