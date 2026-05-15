import unittest
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from handlers import booking


class FakeState:
    def __init__(self, data=None, state=None):
        self.data = dict(data or {})
        self.state = state
        self.cleared = False

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def set_state(self, state):
        self.state = state

    async def get_state(self):
        return self.state

    async def clear(self):
        self.cleared = True
        self.data.clear()
        self.state = None


class FakeMessage:
    photo = None
    reply_markup = None

    def __init__(self, user_id=None):
        if user_id is not None:
            self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.edits = []

    async def answer(self, text, reply_markup=None, parse_mode=None):
        self.answers.append(
            {"text": text, "reply_markup": reply_markup, "parse_mode": parse_mode}
        )

    async def edit_text(self, text, reply_markup=None, parse_mode=None):
        self.edits.append(
            {"text": text, "reply_markup": reply_markup, "parse_mode": parse_mode}
        )

    async def edit_caption(self, caption, reply_markup=None, parse_mode=None):
        self.edits.append(
            {"text": caption, "reply_markup": reply_markup, "parse_mode": parse_mode}
        )

    async def edit_reply_markup(self, reply_markup=None):
        self.reply_markup = reply_markup


class FakeCallback:
    def __init__(self, user_id=1, data="confirm_10_20_2026-05-10_09:00"):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeMessage()
        self.bot = object()
        self.data = data
        self.answers = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append({"text": text, "show_alert": show_alert})


def complete_temp_order(**overrides):
    payload = {
        "is_for_other": False,
        "fullname": "Ali Valiyev",
        "phonenumber": "+998901234567",
        "service_id": "10",
        "service_name": "Haircut",
        "barber_id": "20",
        "barber_id_name": "Barber One",
        "date": date(2026, 5, 10),
        "time": time(9, 0),
        "selected_barber_locked": False,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def created_order(**overrides):
    payload = {
        "id": 55,
        "fullname": "Ali Valiyev",
        "phonenumber": "+998901234567",
        "service_id": "10",
        "service_name": "Haircut",
        "barber_id": "20",
        "barber_id_name": "Barber One",
        "date": date(2026, 5, 10),
        "time": time(9, 0),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class BookingConfirmationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger_patches = [
            patch.object(booking.logger, "info"),
            patch.object(booking.logger, "error"),
            patch.object(booking.logger, "exception"),
        ]
        for logger_patch in self.logger_patches:
            logger_patch.start()

    def tearDown(self):
        for logger_patch in reversed(self.logger_patches):
            logger_patch.stop()

    async def test_normal_booking_flow_creates_order(self):
        state = FakeState()
        callback = FakeCallback()
        temp_order = complete_temp_order()
        order = created_order()

        with (
            patch.object(booking, "get_temporary_order", AsyncMock(return_value=temp_order)),
            patch.object(booking, "_calculate_available_slots", AsyncMock(return_value=["09:00"])),
            patch.object(booking, "get_user", AsyncMock(return_value=SimpleNamespace())),
            patch.object(booking, "save_user", AsyncMock(return_value=SimpleNamespace())),
            patch.object(booking, "finalize_temporary_order", AsyncMock(return_value=order)) as finalize_mock,
            patch.object(booking, "notify_barber_realtime", AsyncMock()),
            patch.object(booking, "_render_booking_success", AsyncMock()) as render_mock,
            patch.object(booking, "get_main_menu", return_value="main-menu"),
        ):
            result = await booking.process_booking_confirmation(1, state, callback)

        self.assertTrue(result)
        finalize_mock.assert_awaited_once_with(1)
        render_mock.assert_awaited_once()
        self.assertTrue(state.cleared)
        self.assertEqual(callback.message.answers[-1]["text"], "🏠 Asosiy menyu:")

    async def test_missing_data_shows_error_and_does_not_finalize(self):
        state = FakeState()
        callback = FakeCallback()
        temp_order = complete_temp_order(phonenumber=None)

        with (
            patch.object(booking, "get_temporary_order", AsyncMock(return_value=temp_order)),
            patch.object(booking, "finalize_temporary_order", AsyncMock()) as finalize_mock,
        ):
            result = await booking.process_booking_confirmation(1, state, callback)

        self.assertFalse(result)
        finalize_mock.assert_not_awaited()
        self.assertTrue(callback.answers[-1]["show_alert"])
        self.assertIn("to'liq emas", callback.answers[-1]["text"])

    async def test_cancel_pauses_booking_without_deleting_temp_order(self):
        state = FakeState(state=booking.UserState.waiting_for_barber.state)
        message = FakeMessage(user_id=1)

        with (
            patch.object(booking, "upsert_temporary_order", AsyncMock()) as upsert_mock,
            patch.object(booking, "_delete_temporary_order_safely", AsyncMock()) as delete_mock,
            patch.object(booking, "get_main_menu", return_value="main-menu"),
        ):
            await booking._finish_booking_cancel(message, state)

        upsert_mock.assert_awaited_once_with(
            {
                "user_id": 1,
                "current_state": booking.UserState.waiting_for_barber.state,
            }
        )
        delete_mock.assert_not_awaited()
        self.assertTrue(state.cleared)
        self.assertIn("vaqtincha to'xtatildi", message.answers[-1]["text"])

    async def test_cancel_with_empty_fsm_keeps_existing_db_resume_state(self):
        state = FakeState(state=None)
        message = FakeMessage(user_id=1)
        temp_order = complete_temp_order(current_state=booking.UserState.waiting_for_date.state)

        with (
            patch.object(booking, "get_temporary_order", AsyncMock(return_value=temp_order)) as get_temp_mock,
            patch.object(booking, "upsert_temporary_order", AsyncMock()) as upsert_mock,
            patch.object(booking, "_delete_temporary_order_safely", AsyncMock()) as delete_mock,
            patch.object(booking, "get_main_menu", return_value="main-menu"),
        ):
            await booking._finish_booking_cancel(message, state)

        get_temp_mock.assert_awaited_once_with(1)
        upsert_mock.assert_not_awaited()
        delete_mock.assert_not_awaited()
        self.assertTrue(state.cleared)

    async def test_resume_flow_uses_unified_confirmation(self):
        state = FakeState({booking.PENDING_BOOKING_ENTRY_KEY: {"kind": "root"}})
        callback = FakeCallback()
        temp_order = complete_temp_order()

        with (
            patch.object(booking, "get_temporary_order", AsyncMock(return_value=temp_order)),
            patch.object(booking, "process_booking_confirmation", AsyncMock(return_value=True)) as process_mock,
        ):
            await booking._resume_booking_from_temporary_order(callback, state)

        process_mock.assert_awaited_once_with(
            1,
            state,
            callback,
            answer_text="Booking muvaffaqiyatli yakunlandi ✅",
        )

    async def test_resume_after_cancel_at_booking_target_restores_same_step(self):
        state = FakeState({booking.PENDING_BOOKING_ENTRY_KEY: {"kind": "root"}})
        callback = FakeCallback()
        temp_order = complete_temp_order(
            fullname=None,
            phonenumber=None,
            service_id=None,
            barber_id=None,
            date=None,
            time=None,
            current_state=booking.UserState.waiting_for_booking_target.state,
        )

        with (
            patch.object(booking, "get_temporary_order", AsyncMock(return_value=temp_order)),
            patch.object(booking, "_show_booking_target_prompt", AsyncMock()) as prompt_mock,
        ):
            await booking._resume_booking_from_temporary_order(callback, state)

        prompt_mock.assert_awaited_once_with(callback, state)
        self.assertEqual(callback.answers[-1]["text"], "Booking davom ettirildi ✅")

    async def test_resume_restart_still_deletes_temp_order(self):
        state = FakeState({booking.PENDING_BOOKING_ENTRY_KEY: {"kind": "root"}})
        callback = FakeCallback(data=booking.BOOKING_RESUME_RESTART_CB)

        with (
            patch.object(booking, "_ensure_callback_state", AsyncMock(return_value=True)),
            patch.object(booking, "_delete_temporary_order_safely", AsyncMock()) as delete_mock,
            patch.object(booking, "_restart_booking_from_entry_context", AsyncMock()) as restart_mock,
        ):
            await booking.booking_resume_restart_callback(callback, state)

        delete_mock.assert_awaited_once_with(1)
        restart_mock.assert_awaited_once_with(callback, state, {"kind": "root"})

    async def test_double_confirm_without_temp_order_does_not_create_duplicate(self):
        state = FakeState()
        callback = FakeCallback()

        with (
            patch.object(booking, "get_temporary_order", AsyncMock(return_value=None)),
            patch.object(booking, "finalize_temporary_order", AsyncMock()) as finalize_mock,
        ):
            result = await booking.process_booking_confirmation(1, state, callback)

        self.assertFalse(result)
        finalize_mock.assert_not_awaited()
        self.assertTrue(callback.answers[-1]["show_alert"])

    async def test_db_failure_is_visible_and_state_is_not_cleared(self):
        state = FakeState()
        callback = FakeCallback()
        temp_order = complete_temp_order()

        with (
            patch.object(booking, "get_temporary_order", AsyncMock(return_value=temp_order)),
            patch.object(booking, "_calculate_available_slots", AsyncMock(return_value=["09:00"])),
            patch.object(booking, "get_user", AsyncMock(return_value=SimpleNamespace())),
            patch.object(booking, "save_user", AsyncMock(return_value=SimpleNamespace())),
            patch.object(booking, "finalize_temporary_order", AsyncMock(side_effect=RuntimeError("db down"))),
        ):
            result = await booking.process_booking_confirmation(1, state, callback)

        self.assertFalse(result)
        self.assertFalse(state.cleared)
        self.assertTrue(callback.answers[-1]["show_alert"])
        self.assertIn("xatolik", callback.message.answers[-1]["text"])

    async def test_confirm_persists_selection_then_processes_confirmation(self):
        state = FakeState(
            {
                "fullname": "Ali Valiyev",
                "phonenumber": "+998901234567",
                "is_for_other": False,
            },
            state=booking.UserState.waiting_for_time.state,
        )
        callback = FakeCallback(data="confirm_10_20_2026-05-10_09:00")
        temp_order = complete_temp_order()

        with (
            patch.object(booking, "_ensure_callback_state", AsyncMock(return_value=True)),
            patch.object(booking, "get_temporary_order", AsyncMock(return_value=temp_order)),
            patch.object(booking, "get_user", AsyncMock(return_value=None)),
            patch.object(booking, "_persist_booking_state", AsyncMock()) as persist_mock,
            patch.object(booking, "process_booking_confirmation", AsyncMock(return_value=True)) as process_mock,
        ):
            await booking.confirm(callback, state)

        persist_mock.assert_awaited_once()
        process_mock.assert_awaited_once_with(
            1,
            state,
            callback,
            answer_text="Vaqt tanlandi ✅",
        )

    async def test_confirm_does_not_recreate_missing_temporary_order(self):
        state = FakeState(
            {
                "fullname": "Ali Valiyev",
                "phonenumber": "+998901234567",
                "is_for_other": False,
            },
            state=booking.UserState.waiting_for_time.state,
        )
        callback = FakeCallback(data="confirm_10_20_2026-05-10_09:00")

        with (
            patch.object(booking, "_ensure_callback_state", AsyncMock(return_value=True)),
            patch.object(booking, "get_temporary_order", AsyncMock(return_value=None)),
            patch.object(booking, "_persist_booking_state", AsyncMock()) as persist_mock,
            patch.object(booking, "process_booking_confirmation", AsyncMock(return_value=False)) as process_mock,
        ):
            await booking.confirm(callback, state)

        persist_mock.assert_not_awaited()
        process_mock.assert_awaited_once_with(
            1,
            state,
            callback,
            answer_text="Vaqt tanlandi ✅",
        )


if __name__ == "__main__":
    unittest.main()
