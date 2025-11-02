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
