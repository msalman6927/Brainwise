"""Delete a tagged e2e user; FK cascade removes their topics/messages/questions.

Runs in a fresh interpreter so conftest's placeholder database_url does not apply
and Settings reads the real .env. SelectorEventLoop is required for psycopg on Windows.
"""

import asyncio
import sys

from sqlalchemy import delete, func, select

from backend.db.session import SessionLocal
from backend.models.user import User


async def main() -> None:
    email = sys.argv[1]
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.email == email))
        await db.commit()
        remaining = (
            await db.execute(select(func.count()).select_from(User).where(User.email == email))
        ).scalar_one()
    print(f"remaining={remaining}")
    if remaining:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop())
