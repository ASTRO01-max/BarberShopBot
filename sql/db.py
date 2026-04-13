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
        await conn.execute(
            text(
                """
                ALTER TABLE start_vd_or_img
                ADD COLUMN IF NOT EXISTS vd_file_id VARCHAR(300)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE start_vd_or_img
                ADD COLUMN IF NOT EXISTS img_file_id VARCHAR(300)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE info_expanded
                ADD COLUMN IF NOT EXISTS phone_number2 VARCHAR(30)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE info_profile_settings
                ADD COLUMN IF NOT EXISTS info_id BIGINT
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE info_profile_settings
                ADD COLUMN IF NOT EXISTS hidden_fields JSON NOT NULL DEFAULT '[]'::json
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE info_profile_settings
                SET info_id = 1
                WHERE info_id IS NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ix_info_profile_settings_info_id
                ON info_profile_settings (info_id)
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.table_constraints
                        WHERE table_name = 'info_profile_settings'
                        AND constraint_name = 'info_profile_settings_info_id_fkey'
                    ) THEN
                        ALTER TABLE info_profile_settings
                        DROP CONSTRAINT info_profile_settings_info_id_fkey;
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.table_constraints
                        WHERE table_name = 'info_profile_settings'
                        AND constraint_name = 'info_profile_settings_info_id_fkey'
                    ) THEN
                        ALTER TABLE info_profile_settings
                        ADD CONSTRAINT info_profile_settings_info_id_fkey
                        FOREIGN KEY (info_id) REFERENCES info(id) ON DELETE CASCADE;
                    END IF;
                END $$;
                """
            )
        )
