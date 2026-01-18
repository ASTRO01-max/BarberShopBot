#utils/states.py
from aiogram.fsm.state import StatesGroup, State

from aiogram.fsm.state import StatesGroup, State

class UserState(StatesGroup):
    waiting_for_fullname = State()
    waiting_for_phonenumber = State()
    waiting_for_service = State()
    waiting_for_barber = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_new_fullname = State()
    waiting_for_new_phone = State()   # 🔹 shu state yo‘q bo‘lgani uchun xato chiqyapti


class AdminStates(StatesGroup):
    adding_admin_fullname = State()
    adding_admin_phone = State()
    adding_service = State()
    adding_barber = State()
    adding_barber_photo = State()
    adding_photo_choice = State()      #Barber rasmini kutish
    adding_service = State()           # Servis nomini kutish
    adding_service_price = State()     # Servis narxini kutish
    adding_service_duration = State() 
    waiting_for_message = State()  
    adding_barber_fullname = State()
    adding_barber_phone = State()
    adding_barber_experience = State()
    adding_barber_work_days = State()
    adding_barber_work_time = State()
    adding_barber_breakdown = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class UserForm(StatesGroup):
    fullname = State()
    phone = State()
