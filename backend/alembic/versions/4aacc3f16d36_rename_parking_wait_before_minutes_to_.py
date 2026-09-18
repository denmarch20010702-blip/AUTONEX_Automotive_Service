"""rename parking_wait_before_minutes to parking_wait_minutes

Revision ID: 4aacc3f16d36
Revises: 41f8d31fc7be
Create Date: 2026-09-17 20:45:08.986830

"""
from alembic import op
import sqlalchemy as sa


revision = '4aacc3f16d36'
down_revision = '41f8d31fc7be'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Настоящее переименование (не add+drop, который автогенерация выдала
    # по умолчанию) — значение поля не теряется, что важно, раз это уже
    # реальная колонка с данными на живой станции, а не только в тестах.
    op.alter_column('bookings', 'parking_wait_before_minutes', new_column_name='parking_wait_minutes')


def downgrade() -> None:
    op.alter_column('bookings', 'parking_wait_minutes', new_column_name='parking_wait_before_minutes')
