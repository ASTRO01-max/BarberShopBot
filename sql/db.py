#sql/db.py
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# Yangi UTF-8 baza bilan ulanish
DATABASE_URL = "postgresql+asyncpg://postgres:1234@127.0.0.1:5432/barbershop_utf8"


engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def init_db():
    from . import models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                """
                ALTER TABLE service_discounts
                ADD COLUMN IF NOT EXISTS applied_scope VARCHAR(20) NOT NULL DEFAULT 'single'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE service_discounts
                ADD COLUMN IF NOT EXISTS end_at DATE
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE service_discounts
                ADD COLUMN IF NOT EXISTS end_time TIME
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE service_discounts
                SET
                    end_at = (
                        (
                            COALESCE(updated_at, created_at, NOW())
                            AT TIME ZONE 'Asia/Tashkent'
                        ) + INTERVAL '24 hours'
                    )::date,
                    end_time = (
                        (
                            COALESCE(updated_at, created_at, NOW())
                            AT TIME ZONE 'Asia/Tashkent'
                        ) + INTERVAL '24 hours'
                    )::time(0)
                WHERE end_at IS NULL OR end_time IS NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE service_discounts
                ALTER COLUMN end_at SET NOT NULL,
                ALTER COLUMN end_time SET NOT NULL
                """
            )
        )
