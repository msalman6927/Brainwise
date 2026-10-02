"""Full-stack journey against a real uvicorn + real PostgreSQL + real OpenAI (AGENTS.md §9).

Exactly five model calls per journey run: Q1 + Q2 + Q3 + one explanation + one
follow-up reply. Everything else (envelopes, 409s, history replay, delete) is LLM-free.
The tagged probe user is deleted afterwards via a fresh-interpreter cleanup script.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PORT = 8014
BASE_URL = f"http://127.0.0.1:{PORT}"
IQ_TO_LEVEL = {85: "Foundation", 95: "Basic", 110: "Intermediate", 128: "Advanced"}
TERMINAL = {"done", "error"}


# conftest's placeholder and any stale API key must not reach spawned processes;
# without them the child falls back to the real backend/.env.
_STRIPPED_KEYS = {"database_url", "openai_api_key"}


def _server_env() -> dict[str, str]:
    # Windows env vars are case-insensitive (os.environ stores DATABASE_URL), but a
    # copied plain dict is not — filter case-insensitively or the placeholder leaks.
    return {k: v for k, v in os.environ.items() if k.lower() not in _STRIPPED_KEYS}


@pytest.fixture(scope="session")
def live_server() -> Iterator[str]:
    log_path = Path(os.environ.get("TEMP", ".")) / "brainwise_e2e_server.log"
    log = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--reload",
        ],
        cwd=BACKEND_ROOT,
        env=_server_env(),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 90
        up = False
        while time.monotonic() < deadline and proc.poll() is None:
            try:
                if httpx.get(f"{BASE_URL}/api/v1/health", timeout=1.0).status_code == 200:
                    up = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        if not up:
            log.close()
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"e2e server failed to start; log tail:\n{tail}")
        # Touch the database before the tests: a cold Neon resume can exceed any
        # per-request budget, and the first DB call should absorb that, not a test.
        warm_email = f"e2e-warm-{uuid.uuid4().hex[:8]}@example.com"
        try:
            with httpx.Client(
                base_url=BASE_URL, timeout=httpx.Timeout(180.0, connect=30.0)
            ) as warm:
                resp = warm.post(
                    "/api/v1/auth/register",
                    json={"email": warm_email, "password": "passw0rd1", "name": "Warmup"},
                )
                resp.raise_for_status()
        finally:
            _cleanup(warm_email)
        yield BASE_URL
    finally:
        log.close()
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)


def parse_sse(raw: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        name: str | None = None
        data: dict[str, Any] | None = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        assert name is not None and data is not None, f"malformed frame: {block!r}"
        events.append((name, data))
    return events


def _assert_healthy_stream(events: list[tuple[str, dict[str, Any]]]) -> None:
    terminals = [name for name, _ in events if name in TERMINAL]
    assert len(terminals) == 1, f"expected exactly one terminal frame, got {terminals}"
    assert events[-1][0] in TERMINAL, "stream must end with done or error"
    if events[-1][0] == "error":
        raise AssertionError(f"stream ended with error frame: {events[-1][1]}")


async def chat(
    client: httpx.AsyncClient, token: str, body: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    headers = {"Authorization": f"Bearer {token}"}
    timeout = httpx.Timeout(180.0, connect=10.0)
    async with client.stream(
        "POST", "/api/v1/chat", json=body, headers=headers, timeout=timeout
    ) as resp:
        assert resp.status_code == 200, f"SSE must start with 200, got {resp.status_code}"
        assert resp.headers["content-type"].startswith("text/event-stream")
        raw = ""
        async for chunk in resp.aiter_text():
            raw += chunk
    events = parse_sse(raw)
    _assert_healthy_stream(events)
    return events


async def expect_chat_error(
    client: httpx.AsyncClient, token: str | None, body: dict[str, Any], status: int, code: str
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = await client.post("/api/v1/chat", json=body, headers=headers)
    assert resp.status_code == status, resp.text
    error = resp.json()["error"]
    assert error["code"] == code, error
    return error


async def register(client: httpx.AsyncClient, email: str) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd1", "name": "E2E Student"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _cleanup(email: str) -> None:
    subprocess.run(
        [sys.executable, str(BACKEND_ROOT / "tests" / "e2e_cleanup.py"), email],
        env=_server_env(),
        cwd=BACKEND_ROOT,
        capture_output=True,
        timeout=180,
    )


def _options_distinct(options: dict[str, str]) -> bool:
    return len({text.strip().lower() for text in options.values()}) == 4


async def test_topics_crud_against_real_db(live_server: str) -> None:
    """LLM-free: auth + topics over real HTTP and real PostgreSQL."""
    email = f"e2e-topics-{uuid.uuid4().hex[:8]}@example.com"
    try:
        async with httpx.AsyncClient(
            base_url=live_server, timeout=httpx.Timeout(180.0, connect=30.0)
        ) as client:
            tokens = await register(client, email)
            headers = {"Authorization": f"Bearer {tokens['access']}"}
            resp = await client.post(
                "/api/v1/topics", json={"title": "  Linear Algebra "}, headers=headers
            )
            assert resp.status_code == 200
            topic = resp.json()
            assert topic["title"] == "Linear Algebra" and topic["phase"] == "topic_set"
            resp = await client.get(f"/api/v1/topics/{topic['id']}/messages", headers=headers)
            assert resp.status_code == 200 and resp.json() == []
            resp = await client.delete(f"/api/v1/topics/{topic['id']}", headers=headers)
            assert resp.status_code == 204
            resp = await client.get(f"/api/v1/topics/{topic['id']}/messages", headers=headers)
            assert resp.status_code == 404
    finally:
        _cleanup(email)


async def test_full_assessment_journey(live_server: str) -> None:
    """The whole product promise: assess -> score -> explain -> follow-up (5 LLM calls)."""
    email = f"e2e-journey-{uuid.uuid4().hex[:8]}@example.com"
    try:
        async with httpx.AsyncClient(
            base_url=live_server, timeout=httpx.Timeout(180.0, connect=30.0)
        ) as client:
            tokens = await register(client, email)
            token = tokens["access"]

            # Unauthenticated chat -> HTTP envelope, no stream.
            await expect_chat_error(
                client, None, {"topic": "photosynthesis", "message": "hi"}, 401, "unauthorized"
            )

            # Q1 (LLM call 1): medium, medium-difficulty ladder root.
            events = await chat(
                client,
                token,
                {"topic": "photosynthesis", "message": "Teach me photosynthesis"},
            )
            assert [name for name, _ in events][:2] == ["phase", "question"]
            assert events[0][1] == {"phase": "assessing", "question_index": 1, "total": 3}
            q1 = events[1][1]
            assert q1["difficulty"] == "medium"
            assert _options_distinct(q1["options"])
            thread_id = q1["thread_id"]
            assert events[-1] == ("done", {"thread_id": thread_id, "phase": "assessing"})

            # Free text during ASSESSING -> 409 envelope (never reaches the LLM).
            await expect_chat_error(
                client,
                token,
                {"thread_id": thread_id, "message": "can I have a hint?"},
                409,
                "invalid_phase",
            )

            # Q2 (LLM call 2): branches off Q1 correctness -> easy or hard, never medium.
            events = await chat(
                client,
                token,
                {"thread_id": thread_id, "question_id": q1["question_id"], "option": "A"},
            )
            assert events[0][1]["question_index"] == 2
            q2 = events[1][1]
            assert q2["difficulty"] in {"easy", "hard"}
            assert events[-1][1]["phase"] == "assessing"

            # Q3 (LLM call 3): branches off Q2 correctness.
            events = await chat(
                client,
                token,
                {"thread_id": thread_id, "question_id": q2["question_id"], "option": "A"},
            )
            assert events[0][1]["question_index"] == 3
            q3 = events[1][1]
            assert q3["difficulty"] in {"easy", "hard"}

            # Final answer: pure-Python scoring + streamed explanation (LLM call 4).
            events = await chat(
                client,
                token,
                {"thread_id": thread_id, "question_id": q3["question_id"], "option": "A"},
            )
            names = [name for name, _ in events]
            assert names[:3] == ["phase", "phase", "score"], names
            assert events[0][1]["phase"] == "scoring"
            assert events[1][1]["phase"] == "explaining"
            score = events[2][1]
            assert score["iq_score"] in IQ_TO_LEVEL, score
            assert score["level"] == IQ_TO_LEVEL[score["iq_score"]], score
            explanation = "".join(d["delta"] for n, d in events if n == "token")
            assert len(explanation) > 800, f"explanation too short: {len(explanation)}"
            assert events[-1] == ("done", {"thread_id": thread_id, "phase": "follow_up"})

            # Follow-up chat via the agent (LLM call 5).
            events = await chat(
                client,
                token,
                {"thread_id": thread_id, "message": "In plain words, what is chlorophyll?"},
            )
            reply = "".join(d["delta"] for n, d in events if n == "token")
            assert len(reply) > 20, f"follow-up reply too short: {reply!r}"
            assert events[-1] == ("done", {"thread_id": thread_id, "phase": "follow_up"})

            # Answer mode after completion -> 409 envelope.
            await expect_chat_error(
                client,
                token,
                {"thread_id": thread_id, "question_id": q3["question_id"], "option": "A"},
                409,
                "invalid_phase",
            )

            # Score is visible on the thread list.
            resp = await client.get("/api/v1/topics", headers={"Authorization": f"Bearer {token}"})
            mine = next(t for t in resp.json() if t["id"] == thread_id)
            assert mine["iq_score"] == score["iq_score"]
            assert mine["level"] == score["level"]
            assert mine["phase"] == "follow_up"

            # History replay: every phase renders from persisted messages alone.
            resp = await client.get(
                f"/api/v1/topics/{thread_id}/messages", headers={"Authorization": f"Bearer {token}"}
            )
            messages = resp.json()
            phases = {m["phase"] for m in messages}
            assert {"topic_set", "assessing", "explaining", "follow_up"} <= phases
            question_messages = [
                json.loads(m["content"])
                for m in messages
                if m["role"] == "assistant" and m["phase"] == "assessing"
            ]
            assert len(question_messages) == 3
            assert all("question_id" in q and "options" in q for q in question_messages)
            answer_count = sum(
                1 for m in messages if m["role"] == "user" and m["phase"] == "assessing"
            )
            assert answer_count == 3
            explanations = [m for m in messages if m["phase"] == "explaining"]
            assert len(explanations) == 1 and len(explanations[0]["content"]) > 800

            # Soft delete hides the thread.
            resp = await client.delete(
                f"/api/v1/topics/{thread_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 204
            resp = await client.get(
                f"/api/v1/topics/{thread_id}/messages", headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 404
    finally:
        _cleanup(email)
