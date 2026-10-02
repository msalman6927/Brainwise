import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

# Imported before any test module, so this wins over .env and tests never
# open a real database connection.
os.environ.setdefault("database_url", "postgresql://placeholder@localhost:5432/brainwise")

# A stale OPENAI_API_KEY in the shell (Windows user scope) would shadow .env and
# make every live LLM test 401. Tests always use the key from backend/.env.
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("openai_api_key", None)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from backend.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client
