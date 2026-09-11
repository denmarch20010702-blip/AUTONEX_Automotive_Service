"""add booking exclusion constraint

Revision ID: ae05e6da14c0
Revises: dfe1c685b738
Create Date: 2026-09-11 18:05:13.225971

"""
from alembic import op
import sqlalchemy as sa


revision = 'ae05e6da14c0'
down_revision = 'dfe1c685b738'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # btree_gist делает возможным EXCLUDE-ограничение с обычным "=" (post_id)
    # в одном GiST-индексе рядом с оператором пересечения диапазонов "&&".
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # Это и есть конкурентно-безопасное резервирование из шага A4: Postgres
    # физически не даст вставить две заявки на один пост с пересекающимися
    # интервалами времени, независимо от того, сколько запросов пришло
    # одновременно и что происходит в коде приложения. Отменённые заявки
    # исключены из проверки — их слот считается свободным.
    op.execute(
        """
        ALTER TABLE bookings
        ADD CONSTRAINT no_overlapping_bookings
        EXCLUDE USING gist (
            post_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        )
        WHERE (status <> 'CANCELLED')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT no_overlapping_bookings")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
