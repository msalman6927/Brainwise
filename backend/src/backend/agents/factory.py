"""LLM access (AGENTS.md §3, §7): model, question generation, explanation, follow-up agent."""

import logging
from collections.abc import AsyncIterator, Callable

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from backend.agents import prompts
from backend.core.config import settings
from backend.schemas.assessment import Difficulty, GeneratedQuestion, Level

logger = logging.getLogger(__name__)


def get_model(*, temperature: float | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=temperature,
    )


async def call_question_model(
    topic: str, difficulty: Difficulty, ordinal: int, feedback: str | None
) -> GeneratedQuestion:
    """Structured-output call for one question (§5); parsing/validation is pydantic's."""
    structured = get_model(temperature=0.2).with_structured_output(GeneratedQuestion)
    messages = [
        SystemMessage(prompts.QUESTION_WRITER_SYSTEM),
        HumanMessage(prompts.question_user_message(topic, difficulty, ordinal, feedback)),
    ]
    result = await structured.ainvoke(messages)
    return GeneratedQuestion.model_validate(result)


async def stream_explanation(topic: str, iq: int, level: Level) -> AsyncIterator[str]:
    """Yield the depth-matched explanation as text deltas (§8)."""
    messages = [
        SystemMessage(prompts.explanation_system(topic, iq, level)),
        HumanMessage(prompts.explanation_user(topic)),
    ]
    async for chunk in get_model().astream(messages):
        content = chunk.content
        if isinstance(content, str):
            if content:
                yield content
        elif isinstance(content, list):
            for part in content:
                text = part.get("text") if isinstance(part, dict) else part
                if isinstance(text, str) and text:
                    yield text


async def run_followup_agent(
    *,
    system_prompt: str,
    tools: list[BaseTool],
    user_message: str,
    on_delta: Callable[[str], None],
) -> None:
    """Stream the follow-up agent's answer as text deltas via on_delta (§7)."""
    agent = create_agent(get_model(), tools=tools, system_prompt=system_prompt)
    stream = await agent.astream_events(
        {"messages": [{"role": "user", "content": user_message}]},
        version="v3",
        config={"recursion_limit": 12},
    )
    async for message in stream.messages:
        async for delta in message.text:
            if delta:
                on_delta(delta)
    await stream.output()
