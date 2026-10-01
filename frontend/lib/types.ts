export type Phase =
  | "idle" | "topic_set" | "assessing" | "scoring" | "explaining" | "follow_up";

export type Level = "Foundation" | "Basic" | "Intermediate" | "Advanced";
export type Difficulty = "easy" | "medium" | "hard";
export type OptionLetter = "A" | "B" | "C" | "D";

export type ErrorCode =
  | "unauthorized" | "invalid_credentials" | "forbidden" | "not_found"
  | "invalid_phase" | "already_answered" | "unsupported_topic"
  | "rate_limited" | "invalid_request" | "internal";

export interface User {
  id: string; // uuid
  email: string;
  name: string;
  created_at: string; // ISO datetime
}

export interface TokenPair { access: string; refresh: string }
export interface RegisterResponse extends TokenPair { user: User }

export interface Topic {
  id: string;
  title: string;
  phase: Phase;
  iq_score: number | null; // 85 | 95 | 110 | 128 once set
  level: Level | null;
  updated_at: string;
}

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  content: string; // markdown, or JSON string when phase === "assessing" (assistant)
  phase: Phase;
  created_at: string;
}

export interface QuestionOptions {
  A: string; B: string; C: string; D: string;
}

export interface QuestionPayload {
  question_id: string;
  thread_id: string | null;
  difficulty: Difficulty;
  text: string;
  options: QuestionOptions;
}

export interface ScoreResult { iq_score: number; level: Level }

export interface ErrorBody {
  code: ErrorCode;
  message: string;
  details?: Record<string, unknown>;
  retryable: boolean;
}
export interface ErrorEnvelope { error: ErrorBody }

// --- POST /chat request union ---
export interface MessageChatRequest {
  thread_id?: string;
  topic?: string;
  message: string; // 1..4000
}
export interface AnswerChatRequest {
  thread_id: string;
  question_id: string;
  option: OptionLetter;
}
export type ChatRequest = MessageChatRequest | AnswerChatRequest;

// --- SSE event payloads ---
export interface PhaseEvent { phase: Phase; question_index?: number | null; total?: number | null }
export interface TokenEvent { delta: string }
export interface DoneEvent { thread_id: string; phase: Phase }
export interface ErrorEvent { code: ErrorCode; message: string; retryable: boolean }

export type SseEvent =
  | { event: "phase";    data: PhaseEvent }
  | { event: "question"; data: QuestionPayload }
  | { event: "token";    data: TokenEvent }
  | { event: "score";    data: ScoreResult }
  | { event: "done";     data: DoneEvent }
  | { event: "error";    data: ErrorEvent };
