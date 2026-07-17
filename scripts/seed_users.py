"""Create demo users (one end user, one support agent).

Run:  python -m scripts.seed_users
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.models.user import User
from app.services.database import AsyncSessionLocal, init_db

configure_logging()
logger = get_logger(__name__)

DEMO = [
    {"email": "user@example.com", "password": "user-password-123", "is_agent": False},
    {"email": "agent@example.com", "password": "agent-password-123", "is_agent": True},
]


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        for d in DEMO:
            exists = (
                await session.execute(select(User).where(User.email == d["email"]))
            ).scalar_one_or_none()
            if exists:
                logger.info("user_exists", email=d["email"])
                continue
            session.add(
                User(
                    email=d["email"],
                    hashed_password=hash_password(d["password"]),
                    is_agent=d["is_agent"],
                )
            )
            logger.info("user_created", email=d["email"], is_agent=d["is_agent"])
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
