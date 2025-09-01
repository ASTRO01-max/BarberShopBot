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