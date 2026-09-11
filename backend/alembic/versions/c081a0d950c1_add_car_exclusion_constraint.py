"""add car exclusion constraint

Revision ID: c081a0d950c1
Revises: ae05e6da14c0
Create Date: 2026-09-11 19:56:27.973782

"""
from alembic import op
import sqlalchemy as sa


revision = 'c081a0d950c1'
down_revision = 'ae05e6da14c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Баг, найденный вручную: EXCLUDE-ограничение на post_id не мешало одной
    # и той же машине получить пересекающиеся по времени заявки на РАЗНЫХ
    # постах — физически машина не может обслуживаться на трёх постах
    # одновременно. btree_gist уже включён миграцией ae05e6da14c0.
    op.execute(
        """
        ALTER TABLE bookings
        ADD CONSTRAINT no_overlapping_car_bookings
        EXCLUDE USING gist (
            car_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        )
        WHERE (status <> 'CANCELLED')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT no_overlapping_car_bookings")
