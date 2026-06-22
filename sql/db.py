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
    """
    Ma'lumotlar bazasini ishga tushirish va sinxronlashtirish.

    Bot ishga tushganda sql/models.py dagi modellar bilan PostgreSQL bazasini
    avtomatik moslashtiradi (auto_migrate):
      - yangi jadvallar yaratiladi
      - mavjud jadvallar yangilanadi (ustun, tur, indeks, FK, unique)
      - modelda yo'q ustunlar o'chiriladi
      - modelda yo'q jadvallar o'chiriladi
    """
    from . import models  # noqa: F401 — modellarni ro'yxatga olish
    from utils.auto_migrate import auto_migrate

    async with engine.begin() as conn:
        await auto_migrate(conn, Base.metadata, drop_columns=True)
