"""add unique constraint on active parked car

Revision ID: f1cddf6c7e48
Revises: 331b78e7a19f
Create Date: 2026-09-18 16:42:47.572417

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1cddf6c7e48'
down_revision = '331b78e7a19f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # UI_description.md п.49 (2026-09-18, найдено пользователем на практике):
    # физически одна машина не может стоять на двух местах одновременно —
    # но у одной машины может быть несколько собственных заявок (разные
    # услуги на разное время), и раньше вторая заявка той же машины могла
    # получить своё отдельное место, пока первая ещё не освобождена.
    # Частичный unique-индекс — тот же приём, что и `uq_bookings_active_
    # parking_spot_id` (миграция 331b78e7a19f), только по `car_id`.
    op.create_index(
        "uq_bookings_active_parked_car_id",
        "bookings",
        ["car_id"],
        unique=True,
        postgresql_where=sa.text("parking_spot_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_bookings_active_parked_car_id", table_name="bookings")
