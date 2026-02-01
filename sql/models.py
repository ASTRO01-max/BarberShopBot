# sql/models.py
from sqlalchemy import Column, Integer, BigInteger, String, Date, Time, Boolean, JSON, DateTime, Float
from sqlalchemy import LargeBinary
from sqlalchemy.sql import func
from sql.db import Base

#Vaqtinchalik foydalanuvchi
class OrdinaryUser(Base):
    __tablename__ = "ordinary_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    username = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<OrdinaryUser tg_id={self.tg_id}, username={self.username}>"

#USERS foydalanuvchilar
class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    fullname = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

#Buyurtmalar
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    fullname = Column(String(100), nullable=False)
    phonenumber = Column(String(30), nullable=False)
    service_id = Column(String(50), nullable=False)
    barber_id = Column(String(50), nullable=False)
    barber_id_name = Column(String(100), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    booked_date = Column(Date, nullable=False)
    booked_time = Column(Time, nullable=False)

#Admin foydalanuvchilar
class Admins(Base):
    __tablename__ = "admins"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    admin_fullname = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

#Barberlar
class Barbers(Base):
    __tablename__ = "barbers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, nullable=True)
    tg_username = Column(String(255), nullable=True)
    barber_first_name = Column(String(100), nullable=True)
    barber_last_name = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    experience = Column(String(50), nullable=False)
    work_days = Column(String(50), nullable=False)
    work_time = Column(String(20), nullable=True)     # "09:00-18:00"
    is_paused = Column(Boolean, default=False)
    breakdown = Column(String(20), nullable=True)     # "13:00-14:00" yoki None
    is_paused_date = Column(Date, nullable=False)
    
    def __repr__(self):
        return f"<Barber {self.barber_first_name} {self.barber_last_name}>"


class BarberPhotos(Base):
    __tablename__ = "barber_photos"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    barber_id = Column(BigInteger, nullable=False)
    photo = Column(String(300), nullable=True)


#Xizmatlar
class Services(Base):
    __tablename__ = "services"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    price = Column(Integer, nullable=False)
    duration = Column(String(50), nullable=False)

#Super Adminlar
class SuperAdmins(Base):
    __tablename__ = "superadmins"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False)
    super_admin_fullname = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)


class Info(Base):
    __tablename__ = "info"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # Telefon va aloqa kanallari
    telegram = Column(String(150), nullable=True)       # @username yoki link
    instagram = Column(String(150), nullable=True)      # link yoki username
    website = Column(String(200), nullable=True)        # optional
    # Manzil matni (foydalanuvchiga ko'rsatish uchun)
    region = Column(String(120), nullable=True)         # Toshkent, Samarqand...
    district = Column(String(120), nullable=True)       # Chilonzor...
    street = Column(String(200), nullable=True)         # ko'cha/uy
    address_text = Column(String(400), nullable=True)   # “Toshkent, Chilonzor ...”
    # Lokatsiya (xaritada ko'rsatish uchun)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Ish vaqti
    work_time_text = Column(String(200), nullable=True) # “09:00–21:00”

    