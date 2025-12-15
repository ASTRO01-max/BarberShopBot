#utils/init_db.py
from sql.db import init_db
import asyncio

asyncio.run(init_db())
