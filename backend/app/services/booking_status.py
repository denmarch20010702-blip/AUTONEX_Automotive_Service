from __future__ import annotations

from app.models.booking import BookingStatus

# CANCELLED сознательно не участвует в этом графе — отмена закреплена за B4
# со своими правилами (освобождение слота и т.д.), не смешиваем её с A5.
ALLOWED_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.ACCEPTED: {BookingStatus.ON_POST},
    BookingStatus.ON_POST: {BookingStatus.AWAITING_APPROVAL, BookingStatus.READY},
    BookingStatus.AWAITING_APPROVAL: {BookingStatus.READY},
    BookingStatus.READY: {BookingStatus.ISSUED},
    BookingStatus.ISSUED: set(),
    BookingStatus.CANCELLED: set(),
}


def is_transition_allowed(current: BookingStatus, target: BookingStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
