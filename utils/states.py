from aiogram.fsm.state import StatesGroup, State

class UserState(StatesGroup):
    waiting_for_fullname = State()
    waiting_for_phonenumber = State()
    waiting_for_service = State()
    waiting_for_barber = State()
    waiting_for_date = State()
    waiting_for_time = State()

class AdminStates(StatesGroup):
    adding_service = State()
    adding_barber = State()
    adding_service = State()           # Servis nomini kutish
    adding_service_price = State()     # Servis narxini kutish
    adding_service_duration = State() 
    waiting_for_message = State()  

class BroadcastState(StatesGroup):
    waiting_for_message = State()
    