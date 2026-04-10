from aiogram.fsm.state import State, StatesGroup


class UserState(StatesGroup):
    waiting_for_booking_target = State()
    waiting_for_fullname = State()
    waiting_for_phonenumber = State()
    waiting_for_service = State()
    waiting_for_barber = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_new_fullname = State()
    waiting_for_new_phone = State()


class AdminStates(StatesGroup):
    adding_admin_fullname = State()
    adding_admin_phone = State()
    adding_service = State()
    adding_service_price = State()
    adding_service_duration = State()
    adding_service_photo = State()
    adding_barber = State()
    adding_barber_photo = State()
    adding_photo_choice = State()
    waiting_for_message = State()
    adding_barber_fullname = State()
    adding_barber_phone = State()
    adding_barber_experience = State()
    adding_barber_work_days = State()
    adding_barber_work_time = State()
    adding_barber_breakdown = State()


class AdminDiscountStates(StatesGroup):
    selecting_discount_scope = State()
    waiting_for_all_services_percent = State()
    waiting_for_selected_service_percent = State()
    waiting_for_discount_confirmation = State()
    waiting_for_discount_end_date = State()
    waiting_for_discount_end_time = State()


class AdminServiceProfileStates(StatesGroup):
    selecting_field = State()
    waiting_for_field_value = State()
    waiting_for_photo = State()


class BroadcastState(StatesGroup):
    waiting_for_message = State()


class UserForm(StatesGroup):
    fullname = State()
    phone = State()


class BarberPage(StatesGroup):
    waiting_for_work_days = State()
    waiting_for_work_time = State()
    waiting_for_message = State()
    waiting_for_break_time = State()
