# sql/models.py
from sqlalchemy import Column, Integer, BigInteger, String, Date, Time
from sql.db import Base

# class User(Base):
#     __tablename__ = "users"

#     id = Column(BigInteger, primary_key=True, autoincrement=True)  # AUTOINCREMENT yoqilgan
#     tg_id = Column(BigInteger, unique=True, nullable=False)        # Telegram ID
#     fullname = Column(String(255), nullable=True)
#     phone = Column(String(20), nullable=True)

#     def __repr__(self):
#         return f"<User id={self.id}, tg_id={self.tg_id}, fullname={self.fullname}>"

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    fullname = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    fullname = Column(String(100), nullable=False)
    phonenumber = Column(String(30), nullable=False)
    service_id = Column(String(50), nullable=False)
    barber_id = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
