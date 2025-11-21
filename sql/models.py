# sql/models.py
from sqlalchemy import Column, Integer, BigInteger, String, Date, Time
from sqlalchemy import LargeBinary
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


class Barbers(Base):
    __tablename__ = "barbers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False)
    tg_username = Column()
    barber_fullname = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    experience = Column(String(50), nullable=False)
    work_days = Column(String(50), nullable=False)
    photo = Column(LargeBinary, nullable=True)


class Services(Base):
    __tablename__ = "services"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    price = Column(Integer, nullable=False)
    duration = Column(String(50), nullable=False)


class SuperAdmins(Base):
    __tablename__ = "superadmins"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False)
    super_admin_fullname = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

