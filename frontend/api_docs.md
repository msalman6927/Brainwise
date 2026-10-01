# Brainwise — Frontend API & Integration Guide (`api_docs.md`)

> **Audience:** the coding agent / developer building the Brainwise frontend in this folder
> (Next.js 16 App Router, React 19, TypeScript, Tailwind 4).
> **Purpose:** everything needed to design a professional, user-friendly UI and integrate it with
> the FastAPI backend — endpoints, wire formats, streaming contract, error handling, complete UI
> control inventory, and copy-pasteable client code. **You should not need to open a backend
> source file to build the frontend.**
> **Source of truth:** `../backend/AGENTS.md` (spec) + `../backend/src/backend/**` (shapes).
> This document was extracted from them; if you re-verify and find a mismatch, trust the code.

---

## Table of contents

1. [What Brainwise is](#1-what-brainwise-is)
2. [Connect & run](#2-connect--run)
3. [Authentication model](#3-authentication-model)
4. [REST endpoint reference](#4-rest-endpoint-reference)
5. [`POST /chat` — the SSE contract](#5-postchat--the-sse-contract)
6. [State machine → UI matrix](#6-state-machine--ui-matrix)
7. [API-to-UI wiring matrix](#7-api-to-ui-wiring-matrix)
8. [Complete UI inventory (all screens, controls, placeholders)](#8-complete-ui-inventory)
9. [TypeScript types](#9-typescript-types)
10. [Full API client code](#10-full-api-client-code)
11. [Error catalogue](#11-error-catalogue)
12. [Gotchas checklist](#12-gotchas-checklist)
13. [Routing & client state](#13-routing--client-state)
14. [UI/UX specification](#14-uiux-specification)
15. [Out of scope for v1](#15-out-of-scope-for-v1)
16. [Verification checklist](#16-verification-checklist)

---

## 1. What Brainwise is

**Brainwise** is a study bot for students (secondary school → university). The student types a
topic; Brainwise does **not** dump an explanation. It first assesses what the student already
knows, produces a deterministic readiness score ("IQ" band), and only then delivers a complete,
depth-matched explanation — then stays available for follow-up chat.

**The three promises:** **Assess** (exactly 3 adaptive MCQs) → **Score** (deterministic number +
level label) → **Explain** (streamed markdown, calibrated to the level).

```
IDLE ──student submits topic──▶ TOPIC_SET ──bot asks Q1──▶ ASSESSING (Q1..Q3)
   ──Q3 answered──▶ SCORING (pure Python, instant) ──▶ EXPLAINING (streamed markdown)
   ──▶ FOLLOW_UP (free chat, no more assessment) ──new topic──▶ new thread
```

**Assessment design (drives the UI):**

- Exactly **3 questions**, each with **4 options A–D**, exactly one correct.
- Adaptive ladder: Q1 = `medium`. Q2/Q3 = `hard` if the previous answer was correct, else `easy`.
- Difficulty is shown to the student as a small badge (`easy | medium | hard`).
- **No skipping, no going back, no re-attempts** inside one assessment (v1).
- After Q3, the score is computed server-side and revealed as: `iq_score` ∈ {85, 95, 110, 128}
  and `level` ∈ `Foundation | Basic | Intermediate | Advanced`.

| Correct | IQ | Level |
|---:|---:|---|
| 0 / 3 | 85 | Foundation |
| 1 / 3 | 95 | Basic |
| 2 / 3 | 110 | Intermediate |
| 3 / 3 | 128 | Advanced |

**Product rules the UI must respect:**

- Assessment runs **once per topic thread**. `follow_up` never re-assesses. A new topic = a new
  thread = a new assessment.
- Every message in history carries the `phase` it was produced in → **render by phase**.
- The AI explanation is Markdown (headings, bullets, worked examples, tables) and ends with a
  **"Want to go deeper?"** section of 2–3 suggested follow-up questions — render them as clickable
  chips that send themselves.
- Tone: patient, encouraging teacher. Copy should be warm, never clinical or condescending.
- The IQ number is **server-computed only**. Never recompute, never explain how it was derived.

---

## 2. Connect & run

| Item | Value |
|---|---|
| Backend dev command (run from `../backend/`) | `uv run uvicorn backend.main:app --reload` |
| Base URL | `http://localhost:8000` |
| API prefix | `/api/v1` → full base `http://localhost:8000/api/v1` |
| Liveness probe | `GET /api/v1/health` → `{"status":"ok"}` (no auth) |
| Interactive API docs (for manual probing) | `http://localhost:8000/docs` |
| CORS | backend allows origin `http://localhost:3000` with credentials, all methods/headers |
| Frontend dev command (this folder) | `npm run dev` → `http://localhost:3000` |
| Frontend lint | `npm run lint` |

**Environment — create `.env.local` in this folder (gitignored by the scaffold):**

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

Rules:

- Read it as `process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3000/api/v1"` inside
  `lib/api.ts` **only** — never hardcode the URL in components.
- The backend and frontend must both run during development. The frontend must degrade
  gracefully when the backend is down (see §11 `network` handling and §8 global states).
- Tokens are sent in the `Authorization` header (no cookies) → CORS `allow_credentials` does not
  matter for auth; still keep requests same-origin-free (call the API directly, no proxy needed).

---

## 3. Authentication model

JWT **access token (30 minutes)** + **refresh token (7 days)**, HS256, both returned in JSON
bodies. No cookies, no server-side sessions.

### Endpoints

**`POST /auth/register`** → `200`

```json
// request
{ "email": "student@example.com", "password": "study123", "name": "Ayesha" }
```

```json
// response — RegisterResponse (TokenPair + user)
{
  "access": "<jwt>",
  "refresh": "<jwt>",
  "user": { "id": "uuid", "email": "student@example.com", "name": "Ayesha",
            "created_at": "2026-09-30T12:00:00Z" }
}
```

Validation (all → `422` with code `invalid_request`):

- `email`: valid email, trimmed + lowercased server-side. Duplicate →
  `422 invalid_request` with `details.fields = [{loc:"body.email", msg:"email already registered",
  type:"value_error"}]` (note: **not** 409).
- `password`: 8–72 chars, **at least one letter and one digit**, ≤72 bytes UTF-8. Message:
  `"password must contain at least one letter and one digit"`.
- `name`: 1–120 chars after trim.
- Unknown keys in the body are rejected (`extra="forbid"`).

**`POST /auth/login`** → `200` `{ "access": "...", "refresh": "..." }`

- Wrong email or password → `401` code `invalid_credentials`, message
  `"Invalid email or password"` (identical for both cases — never hint whether the account
  exists; the UI should show exactly that message).

**`POST /auth/refresh`** → `200` `{ "access": "...", "refresh": "..." }`

- Body: `{ "refresh": "<jwt>" }`.
- Expired / invalid / wrong token type / deleted user → `401` code `unauthorized`
  (`"Token has expired"` / `"Invalid token"` / `"Invalid token type"` / `"Account no longer exists"`).
- Stateless: the old refresh token stays valid until its own expiry (no rotation revocation).

**`GET /auth/me`** (Bearer) → `200` `{ "id", "email", "name", "created_at" }`; `401 unauthorized`
when the header is missing/malformed (`"Authorization bearer token required"`), expired, wrong
type, or the user no longer exists.

### Header format

```
Authorization: Bearer <access_token>
```

Missing/invalid header → `401 unauthorized`. There is **no** endpoint that accepts a refresh
token in the header.

### Refresh-on-401 algorithm (implement once, in the client — §10)

1. Attach the current access token to every request.
2. On HTTP `401` with code `unauthorized` (and only if not already an auth endpoint and a refresh
   token exists): call `POST /auth/refresh` **once, single-flight** (all concurrent 401s await the
   same promise), store the new pair, retry the original request **once**.
3. If refresh fails → clear tokens, redirect to `/login?next=<current path>`.
4. Never retry a request that itself was the refresh call.

**Recommended token storage:** access token in memory (module variable) + refresh token in
`localStorage` (`brainwise.refresh`). On app boot: if a refresh token exists, call
`POST /auth/refresh` (or `GET /auth/me` after a silent refresh) to hydrate the session before
rendering protected routes. Show a full-page skeleton until hydration resolves.

---

## 4. REST endpoint reference

Base = `http://localhost:8000/api/v1`. All bodies are `application/json`. All request bodies are
strict: **sending an unknown field returns `422 invalid_request`**.

| # | Method | Path | Auth | Success | Purpose |
|---|---|---|---|---|---|
| 1 | `POST` | `/auth/register` | – | `200` | create account → token pair + user |
| 2 | `POST` | `/auth/login` | – | `200` | credentials → token pair |
| 3 | `POST` | `/auth/refresh` | – | `200` | refresh token → new token pair |
| 4 | `GET` | `/auth/me` | ✓ | `200` | current user |
| 5 | `GET` | `/topics` | ✓ | `200` | my threads, newest activity first |
| 6 | `POST` | `/topics` | ✓ | `200` | create empty thread (`phase: "topic_set"`) |
| 7 | `GET` | `/topics/{id}/messages` | ✓ | `200` | ordered message history |
| 8 | `DELETE` | `/topics/{id}` | ✓ | `204` | soft-delete thread (no body) |
| 9 | `POST` | `/chat` | ✓ | `200` SSE | **the conversation endpoint (§5)** |
| 10 | `GET` | `/health` | – | `200` | liveness |

Path params must be valid UUIDs, otherwise `422 invalid_request`.

### 5/6. Topics

**`GET /topics`** → `200`

```json
[
  { "id": "uuid", "title": "Calculus — integrals", "phase": "follow_up",
    "iq_score": 110, "level": "Intermediate",
    "updated_at": "2026-09-30T12:34:56Z" },
  { "id": "uuid", "title": "Photosynthesis", "phase": "assessing",
    "iq_score": null, "level": null,
    "updated_at": "2026-09-30T11:00:00Z" }
]
```

- Sorted by `updated_at` **descending**; soft-deleted threads excluded; `[]` when empty (never 404).
- `iq_score` / `level` are `null` until the assessment completes — render no badge yet.
- `phase` drives what opening the thread shows (§6).

**`POST /topics`** → `200` with the same object, `phase: "topic_set"`, `iq_score: null`.

> You rarely need this: `POST /chat` with `{ "topic": ..., "message": ... }` creates the thread
> server-side in one call. Use `POST /topics` only if you want a thread to appear in the sidebar
> **before** the student types anything. Both flows are valid and documented in §7.

### 7. History

**`GET /topics/{id}/messages`** → `200` (ascending by `created_at`)

```json
[
  { "id": "uuid", "role": "user", "content": "I want to study integrals",
    "phase": "topic_set", "created_at": "..." },
  { "id": "uuid", "role": "assistant",
    "content": "{\"question_id\":\"...\",\"difficulty\":\"medium\",\"text\":\"...\",\"options\":{\"A\":\"...\",\"B\":\"...\",\"C\":\"...\",\"D\":\"...\"},\"thread_id\":\"...\"}",
    "phase": "assessing", "created_at": "..." },
  { "id": "uuid", "role": "user", "content": "The indefinite integral of cos x",
    "phase": "assessing", "created_at": "..." },
  { "id": "uuid", "role": "assistant", "content": "# Integrals ...markdown...",
    "phase": "explaining", "created_at": "..." },
  { "id": "uuid", "role": "user", "content": "Why do we add +C?", "phase": "follow_up",
    "created_at": "..." },
  { "id": "uuid", "role": "assistant", "content": "Because differentiation…",
    "phase": "follow_up", "created_at": "..." }
]
```

- `role` ∈ `user | assistant | system`. You can ignore `system` (never emitted in v1).
- **Critical:** assistant messages produced during `phase: "assessing"` store the question as a
  **JSON string** (a serialized `QuestionPayload`). Parse it and render a question card —
  never show raw JSON. See the restore algorithm in §12.
- User messages produced during `phase: "assessing"` contain the **option text** the student
  picked (not the letter).
- Assistant messages with `phase: "explaining"` are the main Markdown explanation;
  `phase: "follow_up"` are short chat replies (also Markdown).
- `404 not_found` if the thread is missing, soft-deleted, or belongs to another user
  (one generic message: `"Topic not found"`).

### 8. Delete

**`DELETE /topics/{id}`** → `204` empty body; `404 not_found` as above. The row is only soft
deleted — the client must remove it from the sidebar immediately.

### 10. Health

**`GET /health`** → `200` `{ "status": "ok" }`. Use it for a boot connectivity check / a small
status dot in the UI; treat failure as "backend offline" (show the offline banner, §8).

---

## 5. `POST /chat` — the SSE contract

**This is the heart of the app.** One endpoint drives topic start, assessment, scoring,
explanation, and follow-up chat.

- Method `POST`, path `/api/v1/chat`, requires `Authorization: Bearer <access>`.
- Success response: `200`, `Content-Type: text/event-stream`, headers
  `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`.
- The request body is **exactly one of two shapes** (a Pydantic union, `extra="forbid"`).

### Request shapes

**A. Message mode** — start a topic **or** continue a thread:

```json
{ "topic": "Calculus — integrals", "message": "I want to learn this" }
```

```json
{ "thread_id": "uuid", "message": "Why do we add +C?" }
```

- You must send **exactly one** of `topic` / `thread_id`. Sending both or neither →
  `422 invalid_request`, message `"provide exactly one of 'thread_id' or 'topic'"`.
- `message`: 1–4000 chars after trim. It is always persisted (except the resume path, §5.5).

**B. Answer mode** — replying to the current question during `assessing`:

```json
{ "thread_id": "uuid", "question_id": "uuid", "option": "B" }
```

- `option` must be `"A" | "B" | "C" | "D"` (lowercase input is uppercased server-side).
- Sending **message mode** while `phase === "assessing"` → `409 invalid_phase`
  `"Answer the current question instead of sending a message"`. The composer must be disabled
  during `assessing` so this never happens.

### Consuming the stream — do **not** use `EventSource`

`EventSource` is GET-only and cannot send an `Authorization` header, and this API streams from a
`POST`. Use `fetch()` + `ReadableStream` and parse frames yourself — complete implementation in
§10 (`streamChat`).

Frame grammar: frames are separated by a blank line (`\n\n`), each frame is:

```
event: <name>\n
data: <single-line JSON>\n
\n
```

### Event payloads

| event | payload | meaning |
|---|---|---|
| `phase` | `{"phase":"assessing","question_index":1,"total":3}` | phase change; `question_index`/`total` only in assessing, `scoring`/`explaining` arrive without them |
| `question` | `{"question_id":"uuid","thread_id":"uuid","difficulty":"medium","text":"...","options":{"A":"...","B":"...","C":"...","D":"..."}}` | render the MCQ card |
| `token` | `{"delta":"Integrals are"}` | append to the currently streaming assistant bubble |
| `score` | `{"iq_score":110,"level":"Intermediate"}` | reveal score (before any `token` in the finish branch) |
| `done` | `{"thread_id":"uuid","phase":"follow_up"}` | **terminal success** — finalize turn, refresh sidebar |
| `error` | `{"code":"unsupported_topic","message":"...","retryable":true}` | **terminal failure inside the stream** |

Note: `question.thread_id` is always present (even mid-stream) so you can adopt the thread if
`done` never arrives.

### 5.1 Frame sequences per branch (exact — verified by `backend/tests/test_chat_stream.py`)

**Branch: assessment (question emitted)** — request shapes: message-mode start, message-mode on a
`topic_set` thread, or answer-mode returning the next question:

```
phase   {phase:"assessing", question_index: n, total: 3}
question{question_id, thread_id, difficulty, text, options}
done    {thread_id, phase:"assessing"}
```

**Branch: finish (assessment complete → explanation)** — answer-mode on Q3, or resume:

```
phase   {phase:"scoring"}            ← only on the first completion (emit_scoring), skipped on resume
phase   {phase:"explaining"}
score   {iq_score, level}
token   {delta}  × N                 ← streamed markdown, in order, as produced
done    {thread_id, phase:"follow_up"}
```

**Branch: follow-up reply** (`phase === "follow_up"` message mode):

```
token   {delta}  × N                 ← may be preceded by tool-emitted frames (phase/question), rare
done    {thread_id, phase:"follow_up"}   ← or phase:"assessing" if the agent started a NEW topic
```

**Terminal invariant:** every stream ends with **exactly one** `done` **or** one `error`, never
both, never zero. After `error`, no further frames arrive.

**Mid-stream failure:**

```
phase, phase, score, token … , error {code, message, retryable}   ← partial tokens remain visible
```

### 5.2 Errors **before** the first frame = normal HTTP responses

The backend validates eagerly (auth, ownership, grading, question generation). In these cases
**no stream starts** — you get a JSON error envelope with a non-2xx status. Always check
`response.ok` before treating the body as a stream:

| Situation | Status | code |
|---|---|---|
| missing/expired/wrong token | 401 | `unauthorized` |
| thread not found / foreign / deleted | 404 | `not_found` |
| message-mode during `assessing` | 409 | `invalid_phase` |
| answering an already-answered question | 409 | `already_answered` |
| topic cannot be quizzed with MCQs | 422 | `unsupported_topic` (retryable) |
| malformed body / XOR violated / bad uuid | 422 | `invalid_request` |
| question generator unavailable | 500 | `internal` (retryable=false, but safe to offer retry) |

### 5.3 Score reveal ordering

`score` always arrives **before** the first `token` of the explanation. Recommended UX: on
`score`, show the animated IQ/level reveal card; on the first `token`, scroll/fade the reveal into
the message list and start streaming the markdown bubble.

### 5.4 Which branch am I in?

Decide client-side from the current thread `phase` + what you sent (§6), then simply consume
frames until `done`/`error`.

### 5.5 Resume semantics (use these in the UI)

- **Dropped explanation stream:** the thread stays `explaining`. Opening it (or sending any
  message-mode request with `thread_id`) re-enters the finish branch and **regenerates the whole
  explanation** (no `scoring` frame the second time). UI: auto-resume with
  `{"thread_id": ..., "message": "continue"}` — that message is **not persisted** on this path.
- **Interrupted answer:** if the last stored history entry is a user answer with no following
  question (generation failed), re-submitting the same `{thread_id, question_id, option}`
  **regenerates the next question** instead of erroring (documented resume path).
- **Connection drop during follow-up:** the reply was not persisted → show a Retry button that
  re-sends the same message.
- Never leave the composer in an undefined state: exactly one request per thread may be in flight;
  disable Send while streaming and offer Stop (AbortController).

---

## 6. State machine → UI matrix

| `phase` | What the student sees | Enabled controls | Legal next request | Illegal (→ `409 invalid_phase`) |
|---|---|---|---|---|
| `idle` | *(client-only state: no thread selected — dashboard / new-topic form)* | topic input, Start | `POST /chat {topic, message}` or `POST /topics` | — |
| `topic_set` | thread exists, assessment armed; composer with prompt "answer the first question starts automatically" | composer Send | `POST /chat {thread_id, message}` → starts Q1 | answering (no `question_id` yet) |
| `assessing` | question card, `Question n of 3` progress, 4 options, difficulty badge; composer **disabled** | option buttons, Submit answer | `POST /chat {thread_id, question_id, option}` | sending a chat message (`409`), submitting twice (`409 already_answered`) |
| `scoring` | brief "Calculating your level…" spinner (instant server-side; you may see it only as `phase{scoring}`) | none (auto-advances) | *(server-side)* | any student input |
| `explaining` | score reveal → streaming markdown explanation; Stop button | Stop (abort), scroll | *(stream completes)* | sending messages |
| `follow_up` | full chat thread + level/IQ badge; composer active | composer Send, suggested chips, new topic, delete thread | `POST /chat {thread_id, message}` | — (never re-assess in this thread) |

**Transitions the client must never assume:** `follow_up` → `assessing` inside the same thread is
impossible; to study something new, start a **new thread** (or let the follow-up agent switch —
then `done` will carry a **different** `thread_id` with `phase: "assessing"`; navigate to it).

---

## 7. API-to-UI wiring matrix

Every backend API/event mapped to trigger → state change → render. **Do not skip any row.**

| API / event | Trigger in the UI | State change | Render |
|---|---|---|---|
| `POST /auth/register` | Register form submit | set tokens + `user`, clear `next` redirect | redirect to `/` (or `?next=`), toast "Welcome, {name}!" |
| `POST /auth/login` | Login form submit | set tokens | redirect; on `401` show inline banner |
| `POST /auth/refresh` | silent, on boot and on any `401` | rotate tokens (single-flight) | none; on failure → `/login` |
| `GET /auth/me` | app boot (if refresh token exists) | `user` hydrated, `authLoading=false` | header avatar + name; until then full-page skeleton |
| `GET /health` | app boot + status dot click | `backendOnline: boolean` | green/grey dot; on false show offline banner |
| `GET /topics` | dashboard load; after `done`; after delete | `threads: Topic[]` | sidebar/thread list cards (level badge, IQ chip, relative time) |
| `POST /topics` | "New topic" button (empty-thread flow) | prepend thread | navigate to `/chat/{id}` in `topic_set` |
| `GET /topics/{id}/messages` | opening `/chat/{threadId}` | `messages: Message[]`, `hydrating=false` | replay history **by phase** (§12 restore algorithm) |
| `DELETE /topics/{id}` | card 🗑 button → confirm modal | remove from `threads` | card animates out; toast "Thread deleted"; if current thread → navigate `/` |
| `POST /chat` **{topic, message}** | first message on the new-topic form | creates thread + Q1 | optimistic user bubble → SSE: `phase`→progress dots, `question`→MCQ card, `done`→`threadId` adopted, navigate/refresh sidebar |
| `POST /chat` **{thread_id, message}** on `topic_set` | Send in an armed thread | Q1 generated | same as above |
| `POST /chat` **{thread_id, message}** on `follow_up` | Send / clicked suggestion chip | streaming reply | optimistic user bubble → tokens append to assistant bubble → `done` finalizes |
| `POST /chat` **{thread_id, message}** on `scoring`/`explaining` | auto-resume on thread open | re-runs explanation | score (no `scoring` frame) → tokens → `done` |
| `POST /chat` **{thread_id, question_id, option}** | Submit answer | grade + next question or finish | assess branch → next MCQ card + progress `n/3`; finish branch → score reveal → explanation stream |
| SSE `phase` | stream | `phase`, `questionIndex` | update progress chip/dots, enable/disable composer |
| SSE `question` | stream | `currentQuestion` | render MCQ card (options A–D), focus first option |
| SSE `token` | stream | append to `streamingBuffer` | typewriter append inside markdown renderer |
| SSE `score` | stream | `score = {iq_score, level}`, persist onto thread | animated IQ counter + level badge reveal |
| SSE `done` | stream end | finalize message, `phase`, adopt `thread_id`, `streaming=false` | re-fetch `GET /topics` (sidebar badges update); if `phase==="assessing"` with new id → navigate to it |
| SSE `error` | stream end | `streaming=false`, record error | inline error card in the thread with **Retry** if `retryable`, else dismiss + guidance |
| HTTP error (pre-stream) | any call | `streaming=false` | map via §11 (toast / inline field errors / redirect) |

---

## 8. Complete UI inventory

Build **all** of these — no placeholders left empty, no button without a state.

### 8.1 Screens

```
/login            /register           /            /chat/[threadId]
auth card      auth card         dashboard      conversation view
```

### 8.2 Login screen (`/login`)

| Element | Detail |
|---|---|
| Card | logo wordmark "Brainwise", tagline *"Learn any topic, at your level."* |
| Email input | `type=email`, placeholder `you@student.edu`, autoComplete `email` |
| Password input | `type=password`, placeholder `At least 8 characters`, autoComplete `current-password` |
| Show/hide password toggle | icon button, `aria-label="Show password"` |
| **Sign in** button | label → `"Signing in…"` + spinner while pending; disabled until form valid |
| Error banner | shown for `invalid_credentials` / `internal` / network: *"Invalid email or password. Try again or create an account."* |
| Field errors | under each input, from `details.fields[].msg` |
| Link | `"New here? Create an account"` → `/register?next=…` |
| Footer link | `"Back to homepage"` |

### 8.3 Register screen (`/register`)

Same layout plus: **Full name** input (placeholder `e.g. Ayesha Khan`, maxLength 120).
Client-side validation mirrors the server: password ≥8 chars with ≥1 letter + ≥1 digit (live
hint: *"Use 8+ characters with at least one letter and one digit"*), email format, name non-empty.
Duplicate email → field error under email: *"Email already registered"*. Submit button
`"Create account"` → `"Creating your account…"`. Link: *"Already have an account? Sign in"*.

### 8.4 Dashboard (`/`)

| Element | Detail |
|---|---|
| Header | logo, user chip (avatar initial + name), **Log out** button |
| **New topic form** | input placeholder **`"e.g. Photosynthesis, Trigonometry, HTTP caching…"`**, helper text *"Type the topic you want to study — Brainwise will ask 3 quick questions first."*, **Start learning** button (disabled when empty; shows `"Preparing your first question…"` while the SSE start request runs) |
| Filter box | client-side search over loaded threads, placeholder `"Filter your topics…"` |
| Thread list | cards: title, **level badge** (`Foundation/Basic/Intermediate/Advanced`, hidden when null), **IQ chip** (`IQ 110`, hidden when null), phase chip (`Assessing`/`Explaining`/`In conversation`), relative time (`2h ago`), hover actions: **Open**, **Delete** |
| Empty state | illustration/icon + *"No topics yet — what do you want to learn today?"* + the new-topic form focused |
| No-results state | *"No topics match “{query}”"* + clear-filter button |
| Loading | 3 skeleton cards (shimmer) |
| Offline | global banner (§8.6) |

### 8.5 Conversation view (`/chat/[threadId]`)

**Header:** back button (← to `/`), topic title (truncate), **phase chip**, progress
`Question 2 of 3` with 3 dots (only during `assessing`), **level badge + IQ chip** (after score),
**Delete thread** button (opens confirm modal), status dot (health).

**Message list (rendered by phase):**

| `phase` / role | Render as |
|---|---|
| `topic_set` user | user bubble (right) |
| `assessing` assistant (JSON) | **MCQ card**: question text, difficulty badge, 4 option buttons `A`–`D`, Submit; answered state if a user message follows |
| `assessing` user | student-answer chip (right, shows selected option text) |
| `scoring` | centered spinner card *"Calculating your level…"* |
| `explaining` assistant | full-width markdown article + streaming cursor while tokens arrive |
| `follow_up` user/assistant | chat bubbles (right/left), markdown in assistant bubble |

**MCQ card controls:** each option is a `<button>` showing the letter badge + text; states:
`default / hover / focus-visible / selected / disabled / correct / incorrect` (correctness is not
revealed by the API — do not fake it; only disable after submit). Submit button
**"Submit answer"** (disabled until an option is selected), label → `"Checking…"` while streaming.
Note under the card: *"There are 3 questions — no going back."*

**Score reveal:** card with animated counter to `iq_score`, big **level** badge, subtext
*"This sets the depth of your explanation."*, auto-advances when tokens start (or a
**"Continue"** button if you pause it).

**Composer (bottom):**

| Phase | Placeholder | Controls |
|---|---|---|
| `topic_set` | `"Press Send to start your assessment"` | Send |
| `assessing` | *"Answer the question above to continue"* | **disabled** composer (read-only textarea) |
| `explaining` | `"Brainwise is explaining…"` | **Stop** button (aborts the stream) |
| `follow_up` | `"Ask a follow-up about {topic}…"` | Send, char counter near 4000, Stop while streaming |

Send button: icon + `aria-label="Send message"`, disabled when empty or a request is in flight.
Enter sends, Shift+Enter newline. Max 4000 chars (counter turns amber > 3600).

**Suggested follow-up chips:** after the explanation, parse the trailing *"Want to go deeper?"*
section (bullet list of questions at the end of the markdown) and render each as a clickable chip
(`"→ {question}"`) that fills/sends the composer. If parsing finds nothing, fall back to generic
chips: *"Give me a simpler example"*, *"Quiz me again on this"*, *"What should I study next?"*.

**Error card (in-thread):** icon + `message` + **Retry** button when `retryable === true`
(otherwise just **Dismiss**). `unsupported_topic` gets special copy:
*"Brainwise can't quiz this topic yet — try rephrasing it."*

### 8.6 Global elements

- **Toasts** (success/error, top-right, auto-dismiss 4s): account created, thread deleted, copy
  actions, network failures.
- **Confirm modal** (delete thread): title *"Delete “{title}”?"*, body *"This removes the thread
  from your list. It can't be undone."*, buttons **Cancel** / **Delete** (destructive style).
- **Offline banner** (top): *"Can't reach the Brainwise server — is the backend running on
  port 8000?"* + **Retry** (re-runs `GET /health`).
- **Full-page skeleton** during auth hydration.
- **Focus management:** on route change move focus to the main heading; MCQ card receives focus
  when a `question` event arrives.

---

## 9. TypeScript types

Copy into `lib/types.ts`.

```ts
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
```

---

## 10. Full API client code

### 10.1 `lib/api.ts` — fetch wrapper + all REST calls + refresh-on-401

```ts
import type {
  ChatRequest, ErrorEnvelope, Message, RegisterResponse,
  SseEvent, Topic, TokenPair, User,
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

interface ApiOptions extends Omit<RequestInit, "headers"> { auth?: boolean }

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
```

### 10.2 `lib/streamChat.ts` — POST + SSE parser (an async generator)

```ts
import { ApiError, tokens } from "./api";
import type { ChatRequest, SseEvent } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function* streamChat(
  body: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
    cache: "no-store",
  });

  // Failures known before the first frame arrive as a normal HTTP envelope.
  if (!res.ok) throw await (async () => {
    const env = await res.json().catch(() => null);
    return new ApiError(
      res.status,
      env?.error?.code ?? "internal",
      env?.error?.message ?? `Chat failed (${res.status})`,
      env?.error?.retryable ?? false,
      env?.error?.details,
    );
  })();
  if (!res.body) throw new ApiError(500, "internal", "Empty stream response");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const parseBlock = (block: string): SseEvent | null => {
    const lines = block.split("\n");
    const eventLine = lines.find((l) => l.startsWith("event: "));
    const dataLine = lines.find((l) => l.startsWith("data: "));
    if (!eventLine || !dataLine) return null;
    const event = eventLine.slice(7).trim();
    const data = JSON.parse(dataLine.slice(6));
    return { event, data } as SseEvent;
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        if (!block.trim()) continue;
        const parsed = parseBlock(block);
        if (parsed) yield parsed;
      }
    }
  } finally {
    reader.releaseLock();
  }
  // Note: the terminal invariant guarantees you already saw exactly one
  // "done" or "error" before the generator ends. If the connection died
  // first, treat it as a retryable network error in the caller.
}
```

**Typical consumption loop (state machine in the component):**

```ts
const ac = new AbortController();
setStreaming(true);
try {
  for await (const ev of streamChat(request, ac.signal)) {
    switch (ev.event) {
      case "phase":   setPhase(ev.data.phase); setProgress(ev.data.question_index); break;
      case "question": setCurrentQuestion(ev.data); setThreadId(ev.data.thread_id!); break;
      case "score":   setScore(ev.data); break;
      case "token":   appendToken(ev.data.delta); break;
      case "done":    finalize(ev.data.thread_id, ev.data.phase); break;
      case "error":   showError(ev.data); break; // terminal
    }
  }
} catch (e) {
  if ((e as Error).name === "AbortError") showInfo("Stopped.");
  else if (e instanceof ApiError) showError({ code: e.code, message: e.message, retryable: e.retryable });
  else showNetworkError(); // stream dropped — offer Retry
} finally {
  setStreaming(false);
  void topicsApi.list().then(setThreads); // refresh badges (iq/level/phase)
}
```

### 10.3 `lib/restore.ts` — replay history safely

```ts
import type { Message, QuestionPayload } from "./types";

export type ViewItem =
  | { kind: "user"; message: Message }
  | { kind: "assistant-text"; message: Message }
  | { kind: "question"; message: Message; question: QuestionPayload; answered: boolean };

export function toViewItems(messages: Message[]): ViewItem[] {
  const items: ViewItem[] = [];
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.role === "user") { items.push({ kind: "user", message: m }); continue; }
    if (m.phase === "assessing") {
      try {
        const question = JSON.parse(m.content) as QuestionPayload;
        const next = messages[i + 1];
        const answered = next?.role === "user" && next.phase === "assessing";
        items.push({ kind: "question", message: m, question, answered });
      } catch {
        items.push({ kind: "assistant-text", message: m }); // defensive
      }
      continue;
    }
    items.push({ kind: "assistant-text", message: m });
  }
  return items;
}

/** True when history ends with an answer whose next question never arrived →
 *  re-submit the last answer (idempotent resume path, §5.5). */
export function pendingAnswer(messages: Message[]): { question_id: string; option: "A"|"B"|"C"|"D" } | null {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "user" || last.phase !== "assessing") return null;
  const prev = messages[messages.length - 2];
  if (!prev || prev.role !== "assistant" || prev.phase !== "assessing") return null;
  try {
    const q = JSON.parse(prev.content) as QuestionPayload;
    const entry = Object.entries(q.options).find(([, text]) => text === last.content);
    if (!entry) return null;
    return { question_id: q.question_id, option: entry[0] as "A" | "B" | "C" | "D" };
  } catch { return null; }
}
```

**Open-thread algorithm:**

1. `GET /topics/{id}/messages` → build the view with `toViewItems`.
2. Read `topic.phase`:
   - `topic_set` → enable composer ("press Send to start").
   - `assessing` → if the **last** item is an unanswered question card → show it as active.
     Else if `pendingAnswer(...)` returns a value → auto re-submit it via answer mode (resume).
   - `scoring` / `explaining` → auto-resume: `POST /chat {thread_id, message:"continue"}`
     (this message is not persisted), consume the finish branch.
   - `follow_up` → enable composer.

---

## 11. Error catalogue

Envelope (all non-SSE failures):

```json
{ "error": { "code": "invalid_phase", "message": "...", "details": {}, "retryable": false } }
```

422 validation adds `details.fields = [{ "loc": "body.email", "msg": "...", "type": "..." }]`.

| code | HTTP | retryable | UI handling |
|---|---|---|---|
| `unauthorized` | 401 | no | triggers silent refresh; if it fails → redirect `/login` |
| `invalid_credentials` | 401 | no | inline banner on the login form |
| `forbidden` | 403 | no | generic "You don't have access" (reserved; not currently emitted) |
| `not_found` | 404 | no | thread view → "This topic no longer exists" + back to dashboard |
| `invalid_phase` | 409 | no | in-thread card: message + **Reload thread** button (desync recovery) |
| `already_answered` | 409 | no | re-fetch `GET /topics/{id}/messages` and re-render the latest state |
| `unsupported_topic` | 422 | **yes** | prominent card: "Brainwise can't quiz this topic yet — try rephrasing it." + **Retry** + link to dashboard |
| `rate_limited` | 429 | **yes** | toast "Slow down a moment" + auto-retry after 2s (reserved; not currently emitted) |
| `invalid_request` | 422 | no | map `details.fields[].loc` → per-field messages; fallback banner |
| `internal` | 500 | no | in-thread/toast: "Something went wrong" + **Retry** |
| *(network / CORS / backend down)* | — | yes | offline banner + Retry (`GET /health`) |

---

## 12. Gotchas checklist

1. **Strict bodies:** every request model forbids unknown keys → never spread extra fields.
2. **XOR:** message mode needs exactly one of `thread_id`/`topic`.
3. Options are uppercase `A`–`D`; ids are UUID strings.
4. **`question` events carry `thread_id`** — adopt it immediately (start-of-thread flow: you may
   not have an id until this event).
5. **History JSON:** assistant messages with `phase:"assessing"` are a serialized
   `QuestionPayload` string → parse, never render raw.
6. `done` may arrive with a **different `thread_id`** and `phase:"assessing"` (the follow-up agent
   started a new topic) → navigate to the new thread.
7. Every stream ends with exactly one `done` **or** `error`. If neither arrives (connection cut),
   treat as retryable network failure; state on the server is resumable (§5.5).
8. Pre-stream failures are **HTTP envelopes**, not SSE `error` events — check `res.ok` first.
9. `iq_score`/`level` are `null` until scoring; possible values are only 85/95/110/128 and the four
   labels. Never compute or derive them client-side.
10. `GET /topics` returns `[]`, never 404; a foreign/soft-deleted thread is one generic 404.
11. Duplicate registration is `422 invalid_request` with a `body.email` field error — not 409.
12. `DELETE` returns `204` with **no body** — do not `res.json()` it.
13. During `assessing` the composer must be disabled: message-mode → `409 invalid_phase`.
14. Re-submitting an already-answered question → `409 already_answered` (except the resume path).
15. Path params validate as UUIDs → malformed ids give `422`, not 404.
16. Tokens: access 30 min / refresh 7 days — handle `401 unauthorized` proactively (§10.1).
17. Markdown arrives as plain text deltas — render incrementally; don't wait for `done`.
18. Never buffer the whole explanation client-side: append per `token` for a live feel.

---

## 13. Routing & client state

```
app/
├── layout.tsx               # fonts, <AuthProvider>, <ToastProvider>, metadata
├── page.tsx                 # dashboard (protected)
├── login/page.tsx           # public
├── register/page.tsx        # public
└── chat/[threadId]/page.tsx # conversation (protected)
lib/
├── types.ts                 # §9
├── api.ts                   # §10.1
├── streamChat.ts            # §10.2
├── restore.ts               # §10.3
├── markdown.tsx             # markdown renderer + "Want to go deeper?" chip extraction
└── auth.tsx                 # context: user, hydration, login/register/logout
```

- **Auth provider:** on mount → `tokens.load()`; if a refresh token exists → refresh (or `me`) →
  set `user`; else redirect to `/login?next=…`. Expose `{user, loading, login, register, logout}`.
- **Thread store:** `threads: Topic[]`, `activeThreadId`, `phase`, `score`, `question`,
  `streaming: boolean`. Exactly **one in-flight chat request per thread** — disable Send/Submit
  while `streaming`.
- **Middleware/protection:** gate `/` and `/chat/*` client-side (or with Next middleware reading a
  non-httpOnly marker) — the API is the real authority; a 401 mid-session just redirects.
- **Suggested deps** (install only if you use them): `react-markdown` + `remark-gfm` for
  markdown, `lucide-react` for icons, `clsx` for class merging. Tailwind 4 is already configured.
- **Next.js 16 note:** this scaffold's `AGENTS.md` says this version has breaking changes — read
  the relevant guide in `node_modules/next/dist/docs/` before writing routing/server code, and
  keep the `<!-- BEGIN:nextjs-agent-rules -->` block intact.

---

## 14. UI/UX specification

### Design direction

Calm, focused **study/tutor** aesthetic: generous whitespace, readable serif-ish display headings
with a clean sans body (or the scaffold's default font stack), long-form line-height ≥1.6 for
explanations, high-contrast text (WCAG AA), soft card shadows, rounded-2xl surfaces.

Suggested tokens (Tailwind 4 CSS variables in `globals.css`):

```
--background:#f8fafc  --surface:#ffffff  --brand:#4f46e5 (indigo-600)
--accent:#0ea5e9      --success:#16a34a  --warning:#d97706  --danger:#dc2626
--muted:#64748b       --border:#e2e8f0
Level chips: Foundation #f59e0b · Basic #22c55e · Intermediate #3b82f6 · Advanced #a855f7
```

### Layout

- **Desktop:** fixed 280px left sidebar (new-topic form + thread list) / main column max-w-3xl
  centered, sticky header, composer pinned to the bottom.
- **Mobile (<768px):** sidebar becomes a slide-over drawer (hamburger in header); composer sticks
  above the safe area; touch targets ≥44px.

### Per-screen behavior

1. **Auth:** single centered card, logo, form, inline errors, loading on submit, redirect back to
   `?next=`.
2. **Dashboard:** hero line *"What do you want to learn today?"*, prominent new-topic form,
   responsive card grid/list, hover reveal actions, empty/loading/offline states.
3. **Assessment:** card-focused, distraction-free (sidebar dimmed), progress dots top, options as
   large stacked buttons with letter badges, keyboard shortcuts **1–4 or A–D** select,
   **Enter** submits, announce progress via `aria-live="polite"`.
4. **Score reveal:** full-width celebratory-but-restrained card; count-up animation ~800ms; level
   badge scale-in; then auto-scroll to the explanation.
5. **Explanation:** markdown article (h2/h3 spacing, styled lists/tables/code), sticky "level +
   IQ" chip while reading, streaming cursor (blinking block), Stop button visible.
6. **Follow-up:** standard chat ergonomics — user bubbles right (brand tint), assistant left
   (surface), markdown inside assistant bubbles, suggestion chips row above the composer,
   auto-scroll unless the user scrolled up (then show a "Jump to latest" pill).

### Accessibility

- All interactive elements are real `<button>`/`<input>` with visible focus rings.
- `aria-live="polite"` region announcing streamed text (throttle updates) and phase changes.
- Modal: focus trap, Escape closes, return focus to trigger.
- Every icon-only control has an `aria-label`; color is never the only signal (chips carry text).
- Respect `prefers-reduced-motion` (disable count-up/typewriter easing).

### Empty / loading / error states (must all exist)

Dashboard: skeleton cards · no topics · no filter matches · offline banner.
Conversation: hydrating skeleton · generating-question shimmer ("Brainwise is writing question 2…")
· scoring spinner · streaming · stream error card (with Retry) · thread-not-found · offline.

---

## 15. Out of scope for v1

Do not build unprompted: file uploads/RAG, image generation, multi-language UI, voice, spaced
repetition, leaderboards, admin panel, dark-mode requirement (optional extra is fine), WebSocket
transport (SSE only), Docker/K8s deploy configs.

---

## 16. Verification checklist

Run this after building (and use it while reading this doc):

```bash
# backend up (from ../backend/)
uv run uvicorn backend.main:app --reload
# frontend up (from this folder)
npm run dev      # http://localhost:3000
npm run lint
```

Manual journey to verify every wired row:

1. `GET /health` → dot turns green (or offline banner if backend stopped).
2. Register with a weak password → client-side hint; with a duplicate email → field error.
3. Login → lands on dashboard; refresh the page → session persists (`GET /auth/me` or refresh).
4. Submit a topic → sidebar shows the thread, MCQ card renders, progress shows `Question 1 of 3`.
5. Answer all 3 → `scoring` → `score` reveal (85/95/110/128 + level) → explanation streams live.
6. Open the thread from the sidebar → history replays correctly (question cards parsed, not JSON).
7. Ask a follow-up → streamed reply; click a "Want to go deeper?" chip → sends itself.
8. Kill the backend mid-stream → error card/offline banner; restart → Retry works.
9. Send a message during `assessing` (devtools) → `409` is handled gracefully (should be
   impossible via UI, since the composer is disabled).
10. Delete a thread → confirm modal → 204 → card removed → 404 on direct URL.

---

*Extracted from `backend/AGENTS.md` and `backend/src/backend/**` on 2026-09-30. Verified against
`backend/tests/test_chat_stream.py`, `test_auth_endpoints.py`, `test_topics_endpoints.py`,
`test_validation_envelope.py`, and `test_chat_e2e.py`.*
