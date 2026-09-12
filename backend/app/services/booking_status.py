from __future__ import annotations

from app.models.booking import BookingStatus

# B4 перенесён вперёд (2026-09-12) по прямому запросу — клиенту нужна
# возможность отменить свою запись из личного кабинета. Отмена разрешена из
# любого статуса, где работа ещё не выдана клиенту — ISSUED и CANCELLED
# остаются конечными. Слот освобождается автоматически: все проверки
# занятости (car_is_free/get_bookings_overlapping в slots.py) уже исключают
# CANCELLED-заявки, так что отдельная логика "освободить пост" не нужна.
ALLOWED_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.ACCEPTED: {BookingStatus.ON_POST, BookingStatus.CANCELLED},
    BookingStatus.ON_POST: {
        BookingStatus.AWAITING_APPROVAL,
        BookingStatus.READY,
        BookingStatus.CANCELLED,
    },
    BookingStatus.AWAITING_APPROVAL: {BookingStatus.READY, BookingStatus.CANCELLED},
    BookingStatus.READY: {BookingStatus.ISSUED, BookingStatus.CANCELLED},
    BookingStatus.ISSUED: set(),
    BookingStatus.CANCELLED: set(),
}


def is_transition_allowed(current: BookingStatus, target: BookingStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
