# sql/models.py
from sqlalchemy import Column, Integer, BigInteger, String, Date, Time
from .db import Base   # endi aylana bo‘lmaydi, chunki db.py modelni tashqarida import qilmayapti

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    fullname = Column(String(100), nullable=False)
    phonenumber = Column(String(30), nullable=False)
    service_id = Column(String(50), nullable=False)
    barber_id = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)

    def __repr__(self):
        return f"<Order id={self.id} user_id={self.user_id} service={self.service_id}>"
