import asyncio
from sqlalchemy import text
from sql.db import async_session, init_db
from sql.models import Barbers, Services
from database.static_data import barbers, services


async def load_static_data():
    """Boshlang‘ich ma’lumotlarni (services, barbers) faqat bir marta yuklaydi."""
    await init_db()
    async with async_session() as session:
        # Jadvaldagi mavjud yozuvlar sonini tekshiramiz
        service_count = (await session.execute(text("SELECT COUNT(*) FROM services"))).scalar()
        barber_count = (await session.execute(text("SELECT COUNT(*) FROM barbers"))).scalar()

        # Agar allaqachon ma'lumotlar mavjud bo'lsa, hech narsa qilmaymiz
        if service_count > 0 and barber_count > 0:
            print("✅ Boshlang‘ich ma’lumotlar allaqachon mavjud. Yangi ma’lumot yuklanmadi.")
            return

        print("⏳ Boshlang‘ich ma’lumotlar yuklanmoqda...")

        # Xizmatlar
        if service_count == 0:
            for _, (name, price, duration) in services.items():
                session.add(Services(name=name, price=price, duration=duration))

        # Sartaroshlar
        if barber_count == 0:
            for b in barbers:
                session.add(Barbers(
                    barber_fullname=b["name"],
                    experience=b["exp"],
                    work_days=b["days"]
                ))

        await session.commit()
        print("✅ Boshlang‘ich ma’lumotlar muvaffaqiyatli yuklandi.")


if __name__ == "__main__":
    asyncio.run(load_static_data())
