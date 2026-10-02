# Brainwise — Agent Context

> **Purpose of this file:** this is the authoritative context for the AI agent working on this
> backend. Re-read it at the start of every task (e.g. on `/init`). When this file and the code
> disagree, **this file wins for intent**; fix the code. When this file and the user disagree,
> the user wins — then update this file.

---

## 1. Vision

**Brainwise** is a study bot. A student types a topic into a chat interface; Brainwise does not
dump an explanation immediately. It first runs a short assessment to find out what the student
already understands, produces a numeric readiness estimate (reported as an "IQ" band, 85–130),
and only then delivers a complete explanation calibrated to that level.

**The three promises:**

1. **Assess** — ask exactly 3 adaptive multiple-choice questions about the topic.
2. **Score** — convert the result into a deterministic number (85–130) plus a level label.
3. **Explain** — deliver a complete, depth-matched explanation, then stay available for follow-ups.

Audience: students (secondary school through university). Tone: patient, encouraging teacher —
never condescending, never clinical.

**v1 scope:** chat + assessment + explanation + auth + history. No file uploads, no RAG, no
image generation, no multi-language output.

---

## 2. Conversation State Machine

The conversation is a **finite state machine**. Transitions are owned by the **service layer in
Python code** — the LLM is never allowed to decide which phase the conversation is in.

```
IDLE
 └─ student submits topic ──▶ TOPIC_SET            (create thread, status=topic_set)
      └─ bot asks Q1 ────────▶ ASSESSING            (question index 1..3)
           └─ Q3 answered ───▶ SCORING              (pure function, no LLM)
                └─ score set ▶ EXPLAINING           (LLM writes the explanation)
                     └───────▶ FOLLOW_UP            (normal chat, no more assessment)
```

| State | Meaning | Allowed next state |
|---|---|---|
| `IDLE` | No topic chosen yet | `TOPIC_SET` |
| `TOPIC_SET` | Thread created, assessment not started | `ASSESSING` |
| `ASSESSING` | Question *n* has been emitted, awaiting answer | `ASSESSING` (next question) / `SCORING` |
| `SCORING` | All 3 answers in, computing score | `EXPLAINING` |
| `EXPLAINING` | Explanation is being generated/streamed | `FOLLOW_UP` |
| `FOLLOW_UP` | Assessment complete, free chat about this topic | `FOLLOW_UP` / `IDLE` (new topic) |

**Rules:**

- Assessment runs **once per topic thread**. Once a thread reaches `FOLLOW_UP`, never re-assess
  inside that thread. A new topic = a new thread = a new assessment.
- `SCORING` must be instantaneous and deterministic (no model call).
- **Resume:** if the explanation stream drops before `done`, the thread stays in `EXPLAINING`;
  the next chat request re-enters `EXPLAINING` and regenerates the explanation (self-loop), then
  advances to `FOLLOW_UP`.
- Every persisted message carries the `phase` it was produced in; the frontend renders by phase.
- Illegal transitions raise a domain error → HTTP 409 with the error envelope (§9).

---

## 3. Tech Stack & Versions

| Layer | Choice | Notes |
|---|---|---|
| Language | Python **3.14.1** | Pinned in `pyproject.toml` (`requires-python = ">=3.14"`) |
| Package manager | **uv** | All commands in §12 use `uv run` |
| Web framework | **FastAPI** + uvicorn (standard extras) | Async-first |
| Agent runtime | **LangChain v1**: `from langchain.agents import create_agent` | **Never** `AgentExecutor`, **never** `langgraph.prebuilt.create_react_agent` (both deprecated) |
| Tools | `langchain-core` `@tool` decorators | Thin wrappers over services (§7) |
| LLM | `langchain-openai` → `ChatOpenAI` | Provider: **OpenAI**. Default model `gpt-5.6-luna`, override with env `OPENAI_MODEL` |
| ORM | **SQLAlchemy 2.0 async** + **psycopg 3** | `DeclarativeBase`, `Mapped[]`/`mapped_column[]` typing. Driver forced to `postgresql+psycopg` in `db/session.py`; async loops — see the Windows gotcha in §12 |
| Migrations | **Alembic** | Autogenerate + review; never hand-edit applied revisions |
| Database | **PostgreSQL** | DSN in `backend/.env` (Neon). Driver is chosen in code, not in the DSN — see §3/env |
| Auth | JWT **access (30 min) + refresh (7 days)** | `pyjwt` for tokens, `pwdlib`/`bcrypt` for hashing |
| Validation | **Pydantic v2** | Separate request/response schemas from ORM models |
| Streaming | **SSE** (`text/event-stream`) | Contract in §9 |
| Testing | **pytest** + `pytest-asyncio` + `httpx.AsyncClient` | |
| Lint/format | **ruff** (lint + format) | |
| Type check | **mypy** (strict-ish) | |

> **Python 3.14 caveat:** the LangChain ecosystem added 3.14 support in 2026, but a few
> transitive extras still cap at `<3.14`. Before adding any new dependency, run `uv sync` and
> confirm it resolves. If a package refuses to install on 3.14, do **not** silently switch to
> pip — report it to the user and propose either a replacement package or a version pin.

**Environment variables** — `backend/.env` (gitignored, already present). `core/config.Settings`
resolves that file by `__file__`, so boot does **not** depend on the CWD; real environment
variables override file values.

```
database_url=postgresql://...     # bare DSN with libpq params (sslmode=...) — db/session.py
                                  # rewrites the driver to +psycopg; alembic uses sync psycopg
openai_api_key=sk-...             # present
openai_model=gpt-5.6-luna               # optional, defaults to gpt-5.6-luna
jwt_secret=...                    # present (generated, gitignored) — HS256 for access+refresh
jwt_access_ttl_min=30             # default
jwt_refresh_ttl_days=7            # default
```

- Lookup is case-insensitive, but the existing file uses these **lowercase** names — keep them.
- The **repo-root `.env` is empty (0 bytes)**; it is not the Brainwise config file.
- `tests/conftest.py` overrides `database_url` before importing the app, so tests never touch
  the real database. It also drops any shell `OPENAI_API_KEY` so live LLM tests always use the
  `.env` key. When stripping env vars for spawned processes, filter **case-insensitively** —
  Windows env vars are case-insensitive (`DATABASE_URL`), but a copied dict is not.

---

## 4. Repo Layout

```
backend/
├── AGENTS.md                 ← this file
├── README.md
├── pyproject.toml            # deps, [dependency-groups] dev, ruff/mypy/pytest config
├── alembic.ini               # placeholder sqlalchemy.url only — never a real credential
├── alembic/
│   ├── env.py                # async runner; DSN comes from Settings
│   └── versions/             # migration revisions live here
├── tests/
│   ├── conftest.py           # ✅ placeholder database_url + OPENAI key scrub, AsyncClient fixture
│   ├── e2e_cleanup.py        # ✅ fresh-interpreter deletion of tagged probe users
│   ├── test_health.py        # ✅ API smoke
│   ├── test_scoring.py       # ✅ IQ table + level bands (§6)
│   ├── test_schemas.py       # ✅ request/response schema rules
│   ├── test_validation_envelope.py  # ✅ 422 → invalid_request envelope (§9)
│   ├── test_security.py      # ✅ password hashing + JWT round-trip
│   ├── test_auth_endpoints.py # ✅ register/login/refresh/me (§9)
│   ├── test_topics_endpoints.py # ✅ topic CRUD + ownership → single 404 (§9)
│   ├── test_assessment_service.py # ✅ ladder, grading, question gen incl. 2 live calls (§5)
│   ├── test_chat_stream.py   # ✅ SSE frame contract, error placement, terminal invariant (§9)
│   └── test_chat_e2e.py      # ✅ live uvicorn+Neon+OpenAI journey (5 LLM calls)
└── src/backend/
    ├── __init__.py           # console script `backend`
    ├── main.py               # ✅ create_app(), CORS, error handlers, router mounting
    ├── py.typed
    ├── core/
    │   ├── config.py         # ✅ Settings (pydantic-settings, CWD-independent .env path)
    │   ├── errors.py         # ✅ DomainError hierarchy + envelope handlers (§9)
    │   ├── security.py       # ✅ hash/verify password (pwdlib/bcrypt), encode/decode JWT
    │   └── deps.py           # ✅ get_db, get_current_user, require_auth
    ├── db/
    │   ├── base.py           # ✅ DeclarativeBase + naming convention
    │   └── session.py        # ✅ async engine, async_sessionmaker
    ├── models/
    │   ├── __init__.py       # ✅ imports every table module (alembic sees only these)
    │   └── user/topic/message/assessment.py   # ✅ tables (§10)
    ├── schemas/
    │   ├── common.py         # ✅ ErrorCode, StrictModel, normalized email/text, ErrorEnvelope
    │   └── auth/topic/chat/assessment.py      # ✅ request/response + SSE payload models
    ├── agents/
    │   ├── state.py          # ✅ Phase enum + legal transitions (§2)
    │   ├── prompts.py        # ✅ ALL prompt constants — no prompts inline (§8)
    │   ├── tools.py          # ✅ @tool definitions + ToolContext.emit frames, thin (§7)
    │   └── factory.py        # ✅ create_agent / call_question_model / stream_explanation / run_followup_agent (§7)
    ├── services/
    │   ├── assessment.py     # ✅ IQ_TABLE / compute_iq / level_for + question logic (§5, §6)
    │   ├── auth.py           # ✅ register / login / refresh (+ duplicate-email 422 detail)
    │   ├── topics.py         # ✅ thread CRUD, ownership → single 404, soft delete
    │   └── chat.py           # ✅ state machine + agent orchestration + SSE frames (§4)
    └── api/
        ├── router.py         # ✅ mounts /api/v1
        └── v1/
            ├── router.py     # ✅ aggregates the routers below
            ├── health.py     # ✅ GET /api/v1/health
            └── auth/topics/chat.py  # ✅ endpoints (§9), chat = SSE
```

`✅` = implemented and covered by tests/verified boot. Every module above is implemented —
no scaffolds remain.

Two deviations from the original plan, both deliberate:

- Routers live under **`api/v1/`** so a `/api/v2` can be added without touching v1.
- **`db/seed.py` was dropped** (YAGNI) — add it back only when seeding actually exists.

**Layering rule (hard):**

```
api/  →  services/  →  models/ + agents/
 (HTTP)   (business logic)  (data)     (LLM)
```

- Routers parse/validate HTTP and serialize responses. **No business logic, no SQL, no LLM calls.**
- Services own transactions, state transitions, and orchestration.
- Agents own prompts, tools, and the model call only.

---

## 5. Assessment Design

**Exactly 3 multiple-choice questions per topic.** Branching ladder:

```
Q1 = MEDIUM
 ├─ correct ──▶ Q2 = HARD      ├─ correct ──▶ Q3 = HARD
 └─ wrong   ──▶ Q2 = EASY      └─ wrong   ──▶ Q3 = EASY
```

- Difficulty of Q3 branches off the correctness of **Q2**.
- Each question has exactly **4 options (A–D)** and **exactly one correct option**.
- Question generation is **on demand**: one structured-output model call per question — Q1
  at `medium`, then after each answer one call for the next question at the difficulty the
  ladder requires. The response must validate against `schemas.assessment.GeneratedQuestion`
  (4 options, one correct, difficulty echo matching the requested tier); on validation
  failure retry **once** with the errors fed back to the model, then raise
  `UnsupportedTopicError` (§9, retryable). See §8 for the question-writing prompt rules.
- **Grading is exact string/option matching in Python.** The LLM never grades, never scores,
  never sees the raw correctness computation.

**Persistence:** every question, its difficulty, the options, the correct option, and the
student's answer are stored (§10) so the assessment is replayable and auditable.

**Answer submission:** the student sends `{ "question_id": ..., "option": "B" }`. The service
verifies the question belongs to an `ASSESSING` thread owned by the current user, grades it,
stores the result, and returns the next question or the completion signal.

**No skip, no back-navigation, no re-attempts** inside the same assessment in v1.

---

## 6. IQ Guardrail (non-negotiable)

The product name says "IQ". The implementation must **not** let a language model produce that
number.

```python
# services/assessment.py — pure function, unit-tested, no I/O, no LLM
IQ_TABLE: dict[int, int] = {0: 85, 1: 95, 2: 110, 3: 128}

LEVELS: list[tuple[int, str]] = [  # (inclusive lower bound, label)
    (0, "Foundation"),
    (95, "Basic"),
    (110, "Intermediate"),
    (128, "Advanced"),
]


def compute_iq(correct: int) -> int:  # correct in {0,1,2,3}
    return IQ_TABLE[correct]


def level_for(iq: int) -> str: ...
```

| Correct | IQ | Level |
|---|---:|---|
| 0 / 3 | 85 | Foundation |
| 1 / 3 | 95 | Basic |
| 2 / 3 | 110 | Intermediate |
| 3 / 3 | 128 | Advanced |

**Hard rules:**

1. The number comes **only** from `compute_iq()`. It is computed in Python, stored, then handed
   to the model as *context* for tone/depth — never as something to calculate.
2. Prompts must instruct: *"Do not compute, guess, or mention how the score was derived. It is
   given to you."*
3. The API response exposes `iq_score` and `level` as **separate typed fields** produced by the
   service, not parsed out of model text.
4. Unit tests must assert the exact table values above and that no other path can emit a score.

If the user later asks to change the mapping, change **this table + these tests**, not the prompt.

---

## 7. LangChain Tools

Built with `@tool` from `langchain-core`, registered on the agent built by
`langchain.agents.create_agent`.

| Tool | Signature (conceptual) | Responsibility |
|---|---|---|
| `get_thread_context` | `() -> ThreadContext` | Current topic title, phase, prior message summary, assessed level (if any) |
| `start_assessment` | `(topic: str) -> QuestionPayload` | Create thread, generate Q1, set phase `ASSESSING` |
| `submit_answer` | `(question_id: str, option: str) -> AssessmentProgress` | Grade (exact match), persist, return next question or completion |
| `complete_assessment` | `() -> ScoreResult` | Finalise: call `compute_iq()`, set phase `EXPLAINING`, return `{iq, level}` |
| `list_followup_history` | `(limit: int = 10) -> list[MessageOut]` | Recent turns in this thread for continuity |

**Tool rules:**

- Tools are **thin**: validate input shape, delegate to `services/`, return JSON-serialisable
  dicts/Pydantic models. No transactions, no scoring math, no prompt text inside tools.
- Tools must be **idempotent where possible** (`submit_answer` on an already-answered question →
  return stored result, do not double-count).
- Tools never accept the IQ score, the level, or the phase as an argument — those are server
  state, not model inputs.
- Every tool call is logged with `user_id`, `thread_id`, tool name, latency.

**Agent construction** (`agents/factory.py`):

```python
from langchain.agents import create_agent

agent = create_agent(model, tools=TOOLS, system_prompt=SYSTEM_PROMPT)
```

Stream via the agent's streaming API and forward `token` chunks to SSE (§9). Cap tool-loop
steps (`recursion_limit`) and surface a `error` event on limit exhaustion.

**Dispatch model (implemented):** routers never call the LLM directly. `services/chat.py`
`prepare()` inspects `(phase, request shape)` and routes to exactly one branch — assessment
answer (question generation is **eager**, before any frame), scoring (`finish_assessment`,
pure), explanation (`stream_explanation`), or follow-up (`run_followup_agent`). Frames Python
owns (`phase`, `question`, `score`, `done`) come from `chat_events()`; frames emitted by tools
inside the agent loop are pushed onto a `ctx.emit` queue and merged in stream order. Follow-up
streaming uses `agent.astream_events(input, version="v3")` → `async for message in
stream.messages` → `async for delta in message.text`, then `await stream.output()`, with
`recursion_limit: 12`. Failures detected before the first frame (auth, 404, `invalid_phase`,
`already_answered`, question generation incl. `unsupported_topic`) are returned as **HTTP error
envelopes**; failures after streaming begins are delivered as a single in-stream `error` event
(§9).

---

## 8. Prompt Rules

All prompts live in `agents/prompts.py` as module-level constants. **No prompt literals
anywhere else in the codebase.**

**Global:**

- Output language: **English only**, regardless of input language.
- Markdown for explanations (headings, bullet lists, worked examples, short tables).
- Never invent citations, URLs, page numbers, or textbook editions.
- Never state or imply how the IQ number was calculated.
- Address the student as "you"; be encouraging; keep paragraphs short.

**Assessment generation prompt must require:**

- 4 options, one unambiguously correct, plausible distractors at the same difficulty.
- Difficulty tiers `easy | medium | hard` matching the ladder in §5.
- Questions test **understanding of the topic**, not trivia or trick wording.
- Topics that cannot be assessed with MCQ → return a typed `UnsupportedTopicError` rather than
  fabricating questions.

**Explanation prompt must require this skeleton:**

1. **One-line framing** — what this topic is and why it matters.
2. **Core concepts** — each defined in plain language, one idea per paragraph.
3. **Worked example** — concrete, step-by-step.
4. **Common mistakes / misconceptions.**
5. **Quick recap** — 4–6 bullets.
6. **"Want to go deeper?"** — 2–3 suggested follow-up questions the student can click.

**Depth is driven by the assessed level (injected as context, not computed by the model):**

| Level | Expected explanation behaviour |
|---|---|
| Foundation (85) | Analogy-first, zero assumed prerequisites, define every term, short sentences |
| Basic (95) | Everyday examples, minimal formalism, build up notation gently |
| Intermediate (110) | Standard technical treatment, formal definitions, moderate math |
| Advanced (128) | Dense, first-principles, edge cases, connections to adjacent topics, minimal hand-holding |

Length target: 400–800 words unless the student asks otherwise.

---

## 9. API Contract

Base path: `/api/v1`. All authenticated routes require `Authorization: Bearer <access_token>`.

### REST

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/auth/register` | – | `{email, password, name}` → user + token pair |
| `POST` | `/auth/login` | – | credentials → `{access, refresh}` |
| `POST` | `/auth/refresh` | refresh token | → new `{access, refresh}` |
| `GET` | `/auth/me` | ✓ | current user |
| `GET` | `/topics` | ✓ | my threads: `{id, title, phase, iq_score, level, updated_at}` |
| `POST` | `/topics` | ✓ | `{title}` → create thread (`TOPIC_SET`) |
| `GET` | `/topics/{id}/messages` | ✓ | full message history, ordered |
| `DELETE` | `/topics/{id}` | ✓ | soft-delete my thread |
| `POST` | `/chat` | ✓ | **SSE** — main conversational endpoint |
| `GET` | `/health` | – | liveness/readiness |

### SSE events — `POST /chat`

Request body — **exactly one of two shapes** (validated as a union, extras forbidden):

- **message mode:** `{ "thread_id": "uuid", "message": "user text" }` or
  `{ "topic": "..." , "message": "user text"}` to start a new thread
- **answer mode** (during `ASSESSING`, §5): `{ "thread_id": "uuid", "question_id": "uuid",
  "option": "B" }`

Response: `Content-Type: text/event-stream`.

```
event: phase
data: {"phase":"assessing","question_index":1,"total":3}

event: question
data: {"question_id":"uuid","thread_id":"uuid","difficulty":"medium","text":"...","options":{"A":"...","B":"...","C":"...","D":"..."}}

event: token
data: {"delta":"Integrals are"}

event: score
data: {"iq_score":110,"level":"Intermediate"}

event: done
data: {"thread_id":"uuid","phase":"follow_up"}

event: error
data: {"code":"unsupported_topic","message":"...","retryable":true}
```

**Rules:** every stream ends with exactly one `done` **or** one `error`. SSE frames are
newline-terminated (`\n\n`). Partial text is flushed as it arrives — never buffer the whole
explanation. A dropped connection must leave the DB in a consistent, resumable state.

**Error placement:** failures known **before the first frame** (401/404/409, `invalid_request`,
`already_answered`, question generation failures incl. `unsupported_topic`) are returned as a
normal HTTP error envelope — no stream starts. Once streaming has begun, failures are delivered
as an `error` event inside the stream, and no further frames follow. Re-submitting an answer
whose row is already stored but whose next question is missing **regenerates** the question
instead of raising `already_answered` (resume path).

### Error envelope (non-SSE)

```json
{ "error": { "code": "invalid_phase", "message": "...", "details": {}, "retryable": false } }
```

Codes: `unauthorized`, `invalid_credentials`, `forbidden`, `not_found`, `invalid_phase`,
`already_answered`, `unsupported_topic`, `rate_limited`, `invalid_request`, `internal`.

**Request-validation failures (422)** use `invalid_request` with
`details.fields = [{"loc": "body.field", "msg": "...", "type": "..."}]` — never FastAPI's
default `{detail: [...]}` shape. `ResponseValidationError` (a server bug) maps to
`internal` with no leaked schema details.

---

## 10. Database Schema

| Table | Key columns |
|---|---|
| `users` | `id` PK, `email` UNIQUE, `password_hash`, `name`, `created_at` |
| `topics` | `id` PK, `user_id` FK→users, `title`, `phase` (enum §2), `iq_score` NULL, `level` NULL, `created_at`, `updated_at`, `deleted_at` NULL (soft delete, §9) — index on `(user_id, updated_at DESC)` |
| `messages` | `id` PK, `topic_id` FK→topics, `role` (`user`/`assistant`/`system`), `content`, `phase`, `created_at` — index on `(topic_id, created_at)` |
| `assessments` | `id` PK, `topic_id` FK→topics UNIQUE (one per topic), `correct_count` (0–3), `iq_score` NULL, `level` NULL, `status` (`in_progress`/`completed`), `completed_at` NULL |
| `assessment_questions` | `id` PK, `assessment_id` FK, `ordinal` (1–3), `difficulty`, `prompt`, `options` (JSONB `{A,B,C,D}`), `correct_option`, `chosen_option` NULL, `answered_at` NULL — UNIQUE `(assessment_id, ordinal)` |

Conventions: UUID primary keys, `created_at`/`updated_at` server defaults (UTC), `ON DELETE
CASCADE` from topic → messages/questions. All schema changes go through **Alembic**; run
`alembic upgrade head` and verify with a fresh database before claiming a migration works.

The live schema also enforces, in the database: `ordinal`/`correct_count` ranges, option
letters (`A`–`D`), the JSONB key set (`options ? 'A' AND ... ? 'D'`), the
`chosen_option`↔`answered_at` pairing, and `users.email` uniqueness. Enum types store the
lowercase `.value` (`values_callable=enum_values` in `db/base.py`). Parent-side
relationships carry `passive_deletes=True` so the ORM relies on the DB cascade instead of
SELECTing children (relationships are otherwise `lazy="raise"`).

`alembic.ini` keeps a **placeholder** `sqlalchemy.url` only — `alembic/env.py` injects the DSN
from `Settings`. Never paste a real connection string into that file (the sibling
`academy project/alembic.ini` committed one by mistake; don't copy that pattern).

---

## 11. Coding Standards

- **Async everywhere** for DB and HTTP: `AsyncSession`, `httpx`, `await`. No sync SQLAlchemy
  calls inside request handlers.
- **Pydantic v2** for every request/response; ORM models never leave the service layer.
- **Full typing**: annotate all function signatures; `mypy` must pass.
- **Domain errors**, not bare `Exception`: raise `DomainError` subclasses in services; global
  handlers in `core/errors.py` map them to the error envelope (§9).
- **Secrets never in code, never in git.** `.env` is gitignored; settings read from environment.
- **Transactions**: one unit of work per service call; commit explicitly; rollback on error.
- **No print-debugging** — use `logging` with structured context (`user_id`, `thread_id`).
- **No dead abstractions**: don't build plugin systems, generic repositories, or factories for
  functionality that does not exist yet. YAGNI.
- Comments only where the *why* is non-obvious. Never narrate what the code obviously does.

---

## 12. Commands

```bash
# workspace-wide install — ALWAYS from the repo root (see gotcha below)
uv sync --all-packages --all-groups

# everything below runs from backend/
uv run uvicorn backend.main:app --reload  # dev server (port 8000)
uv run ruff format .                      # format FIRST
uv run ruff check . --fix                 # then lint + autofix
uv run mypy src                           # type check (pydantic.mypy plugin is configured)
uv run pytest -q                          # tests
uv run pytest -q tests/test_scoring.py    # targeted
uv run pytest -q tests/test_chat_e2e.py   # live journey: real server+DB+5 LLM calls (valid .env key)
uv run alembic revision --autogenerate -m "message"   # new migration
uv run alembic upgrade head               # apply migrations
```

**Workspace gotcha (verified):** the repo root `pyproject.toml` is a uv workspace with two
members (`fastapi/academy project`, `fastapi/Brainwise/backend`) sharing one `.venv`. A bare
`uv sync` executed **inside** a member prunes the sibling project's packages — it silently
uninstalls `academy-project`, `psycopg`, and `pyjwt`. Always sync workspace-wide from the repo
root with `--all-packages --all-groups`. `uv run <cmd>` inside a member is safe and does not
prune. Lint/type/test tooling lives in `[dependency-groups] dev` and is only installed when the
dev group is synced.

**Windows event-loop gotcha (verified):** psycopg's async driver refuses to run on
`ProactorEventLoop` (it needs `add_reader`), and uvicorn on Windows picks Proactor **unless**
`--reload` or `--workers` > 1 is passed — those run in a subprocess, where uvicorn switches to
`SelectorEventLoop`. Keep `--reload` in the dev command above; never start plain
`uvicorn backend.main:app` on Windows. Any async code that touches the DB outside uvicorn
(for example a script or an async test) must build the loop with
`asyncio.run(..., loop_factory=lambda: asyncio.SelectorEventLoop())` or
`asyncio.Runner(loop_factory=...)`. Do **not** use `WindowsSelectorEventLoopPolicy` — loop
policies are deprecated in 3.14 and removed in 3.16.

**Definition of done for any task:** `ruff check` clean, `mypy src` clean, `pytest -q` green,
server boots (`uv run uvicorn ... --reload` starts without import errors).

---

## 13. Rules for the Agent (you)

**Always:**

1. Read this file first on `/init` or at the start of any non-trivial task.
2. Look at existing code in `src/backend/` before adding new modules — mimic its style and
   naming; this codebase's conventions beat generic conventions.
3. Keep prompts in `agents/prompts.py`, logic in `services/`, HTTP in `api/`, tools thin.
4. Add/extend tests when changing scoring, state transitions, auth, or the SSE contract.
5. Verify with the commands in §12 before saying a task is complete.
6. Update this file when a decision in it changes.

**Never:**

1. Never let the LLM compute the IQ score, choose the phase, or grade an answer (§6).
2. Never use `AgentExecutor` or `langgraph.prebuilt.create_react_agent` (§3).
3. Never put business logic in routers, or SQL in tools.
4. Never invent API endpoints, env vars, or table columns — if it isn't in §9 or §10, it doesn't
   exist yet; ask or add it deliberately.
5. Never commit `.env`, secrets, or `uv.lock` churn unrelated to the task.
6. Never skip migration review — inspect the autogenerated diff before applying it.

**Frontend:** lives in `../frontend` (Next.js 16 / React 19 / Tailwind 4). This file defines the
backend + API contract; treat §9 as the handshake. Do not modify the frontend unless asked.

---

## 14. Out of Scope for v1 (do not build unprompted)

RAG / file uploads, vector stores, multi-language output, voice, spaced repetition, leaderboards,
admin panel, rate limiting beyond a basic in-memory guard, Kubernetes/Docker production deploy
configs, WebSocket transport.

---

*Last updated: 2026-09-29 — chat/SSE layer implemented and verified (86 tests green incl. the
live e2e journey); stack, assessment design, IQ mapping, and SSE contract remain frozen until
the user explicitly changes them.*
