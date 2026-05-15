# sql/models.py

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Date,
    Time,
    Boolean,
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
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
    barber_service_id = Column(
        Integer,
        ForeignKey("barber_services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    barber_id = Column(
        BigInteger,
        ForeignKey("barbers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    service_name = Column(String(100), nullable=False)
    barber_name = Column(String(150), nullable=False)
    booked_price = Column(Integer, nullable=False)
    booked_duration_minutes = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    booked_date = Column(Date, nullable=False)
    booked_time = Column(Time, nullable=False)

    barber_service = relationship("BarberServices", back_populates="orders")
    barber = relationship("Barbers", back_populates="orders")

    @property
    def service_id(self) -> str:
        return str(self.barber_service_id or "")

    @property
    def barber_id_name(self) -> str:
        return self.barber_name


#Vaqtinchalik Navbat ma'lumotlari
class TemporaryOrder(Base):
    __tablename__ = "temporary_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    is_for_other = Column(Boolean, nullable=False, default=False)
    current_state = Column(String(100), nullable=True)
    selected_barber_locked = Column(Boolean, nullable=False, default=False)
    fullname = Column(String(100), nullable=True)
    phonenumber = Column(String(30), nullable=True)
    service_id = Column(String(50), nullable=True)
    barber_id = Column(String(50), nullable=True)
    barber_service_id = Column(
        Integer,
        ForeignKey("barber_services.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    service_name = Column(String(100), nullable=True)
    barber_name = Column(String(150), nullable=True)
    booked_price = Column(Integer, nullable=True)
    booked_duration_minutes = Column(Integer, nullable=True)
    date = Column(Date, nullable=True)
    time = Column(Time, nullable=True)
    booked_date = Column(Date, nullable=True)
    booked_time = Column(Time, nullable=True)

    barber_service = relationship("BarberServices")

    @property
    def barber_id_name(self) -> str | None:
        return self.barber_name

    @barber_id_name.setter
    def barber_id_name(self, value: str | None) -> None:
        self.barber_name = value


#Admin foydalanuvchilar
class Admins(Base):
    __tablename__ = "admins"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    admin_fullname = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    username = Column(String(100), nullable=True)


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

    barber_services = relationship(
        "BarberServices",
        back_populates="barber",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    orders = relationship("Order", back_populates="barber")
    
    def __repr__(self):
        return f"<Barber {self.barber_first_name} {self.barber_last_name}>"

#Barberlar rasimlari
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
    photo = Column(String(300), nullable=True)

    barber_services = relationship(
        "BarberServices",
        back_populates="service",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class BarberServices(Base):
    __tablename__ = "barber_services"
    __table_args__ = (
        UniqueConstraint("barber_id", "service_id", name="uq_barber_services_barber_service"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    barber_id = Column(
        BigInteger,
        ForeignKey("barbers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id = Column(
        BigInteger,
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price = Column(Integer, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    barber = relationship("Barbers", back_populates="barber_services")
    service = relationship("Services", back_populates="barber_services")
    discounts = relationship(
        "BarberServiceDiscounts",
        back_populates="barber_service",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    orders = relationship("Order", back_populates="barber_service")


#Barber xizmatlariga chegirmalar
class BarberServiceDiscounts(Base):
    __tablename__ = "barber_service_discounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    barber_service_id = Column(
        Integer,
        ForeignKey("barber_services.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    discount_percent = Column(Numeric(5, 2), nullable=False)
    discounted_price = Column(Integer, nullable=False)
    applied_scope = Column(String(20), nullable=False, server_default="single")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    end_at = Column(Date, nullable=False)
    end_time = Column(Time, nullable=False)

    barber_service = relationship("BarberServices", back_populates="discounts")


#Xizmatlar Profili
# class ServiceProfileSettings(Base):
#     __tablename__ = "service_profile_settings"



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
    # Aloqa kanallari
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


class InfoExpanded(Base):
    __tablename__ = "info_expanded"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(30), nullable=True)
    phone_number2 = Column(String(30), nullable=True)

    def __repr__(self):
        return f"<InfoExpanded id={self.id} phone_number={self.phone_number} phone-number2={self.phone_number2}>"


class InfoProfileSettings(Base):
    __tablename__ = "info_profile_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    info_id = Column(
        BigInteger,
        ForeignKey("info.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    hidden_fields = Column(JSON, nullable=False, default=list)


class BarberOrderInbox(Base):
    __tablename__ = "barber_order_inbox"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Order ID (orders.id)
    order_id = Column(Integer, nullable=False, index=True)

    # Barber telegram id (Barbers.tg_id)
    barber_tg_id = Column(BigInteger, nullable=False, index=True)

    # Barberga telegramda yuborildimi?
    is_delivered = Column(Boolean, default=False)

    # Barber ko�rdimi? (detail bosdi yoki yopdi)
    is_seen = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())



class BarberProfileSettings(Base):
    __tablename__ = "barber_profile_settings"

    barber_id = Column(
        BigInteger,
        ForeignKey("barbers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    hidden_fields = Column(JSON, nullable=False, default=list)
    

class StartVdOrImg(Base):
    __tablename__ = "start_vd_or_img"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vd_file_id = Column(String(300), nullable=True)
    img_file_id = Column(String(300), nullable=True)
    
