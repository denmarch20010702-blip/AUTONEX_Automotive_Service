"""add service_id and scheduled_booking_id to additional_works

Revision ID: b0dec29c14ba
Revises: 707ca94922e7
Create Date: 2026-09-14 21:33:35.807843

"""
from alembic import op
import sqlalchemy as sa


revision = 'b0dec29c14ba'
down_revision = '707ca94922e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "additional_works",
        sa.Column("service_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "additional_works",
        sa.Column("scheduled_booking_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_additional_works_service_id",
        "additional_works",
        "services",
        ["service_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_additional_works_scheduled_booking_id",
        "additional_works",
        "bookings",
        ["scheduled_booking_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_additional_works_scheduled_booking_id", "additional_works", type_="foreignkey"
    )
    op.drop_constraint("fk_additional_works_service_id", "additional_works", type_="foreignkey")
    op.drop_column("additional_works", "scheduled_booking_id")
    op.drop_column("additional_works", "service_id")
