"""make financial history auditable

Revision ID: 72e0c34b4af1
Revises: 4aacc3f16d36
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa


revision = "72e0c34b4af1"
down_revision = "4aacc3f16d36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `total_price` used to be the only financial snapshot.  Preserve every
    # historical amount and explicitly record that no parking breakdown was
    # available for records created before C7's financial hardening.
    op.add_column(
        "booking_archive",
        sa.Column("service_price", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
    )
    op.add_column(
        "booking_archive",
        sa.Column("parking_surcharge", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
    )
    op.add_column(
        "booking_archive",
        sa.Column("parking_wait_minutes", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute("UPDATE booking_archive SET service_price = total_price, parking_surcharge = 0, parking_wait_minutes = 0")
    op.alter_column("booking_archive", "service_price", server_default=None)
    op.alter_column("booking_archive", "parking_surcharge", server_default=None)
    op.alter_column("booking_archive", "parking_wait_minutes", server_default=None)

    # A negative tariff turns parking into an unintended discount.  Normalise
    # any pre-existing invalid value before the database starts enforcing the
    # business invariant as a final line of defence after API validation.
    op.execute(
        "UPDATE station_settings "
        "SET parking_overdue_rate_per_minute = 0 "
        "WHERE parking_overdue_rate_per_minute < 0"
    )
    op.create_check_constraint(
        "ck_station_settings_parking_overdue_rate_non_negative",
        "station_settings",
        "parking_overdue_rate_per_minute >= 0",
    )

    # The aggregate is retained as a legacy cache, but the API reads revenue
    # from the immutable issued archive.  Reconcile the old counter once so
    # diagnostic SQL and historic installations no longer retain corruption
    # caused by tests that previously ran against the live database.
    # `Enum(BookingStatus, name="booking_status")` stores the Python member
    # NAME (`ISSUED`), not its lowercase `.value` — the raw-SQL literal here
    # must match that, or Postgres rejects it as an invalid enum input.
    op.execute(
        "UPDATE station_stats SET total_revenue = COALESCE(("
        "SELECT SUM(total_price) FROM booking_archive WHERE status = 'ISSUED'"
        "), 0) WHERE id = 1"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_station_settings_parking_overdue_rate_non_negative",
        "station_settings",
        type_="check",
    )
    op.drop_column("booking_archive", "parking_wait_minutes")
    op.drop_column("booking_archive", "parking_surcharge")
    op.drop_column("booking_archive", "service_price")
