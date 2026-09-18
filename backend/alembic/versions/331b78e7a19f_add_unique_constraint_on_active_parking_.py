"""add unique constraint on active parking spot assignment

Revision ID: 331b78e7a19f
Revises: 72e0c34b4af1
Create Date: 2026-09-18 14:23:25.971507

"""
from alembic import op
import sqlalchemy as sa


revision = '331b78e7a19f'
down_revision = '72e0c34b4af1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Найдено при код-ревью (2026-09-18): в отличие от постов (защищены
    # `EXCLUDE USING gist` по диапазону времени, см. `no_overlapping_bookings`),
    # места на парковке ничем не защищены от того, что два кода одновременно
    # присвоят один и тот же `parking_spot_id` — сейчас единственная защита
    # это дисциплина `FOR UPDATE` внутри `assign_parking_spot` (parking.py),
    # но это конвенция, а не гарантия на уровне БД. Место занято ровно одной
    # активной заявкой в любой момент (не диапазон времени, как у постов) —
    # достаточен простой частичный unique-индекс, не gist.
    op.create_index(
        "uq_bookings_active_parking_spot_id",
        "bookings",
        ["parking_spot_id"],
        unique=True,
        postgresql_where=sa.text("parking_spot_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_bookings_active_parking_spot_id", table_name="bookings")
