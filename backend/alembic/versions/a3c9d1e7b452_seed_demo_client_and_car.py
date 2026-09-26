"""seed demo client and car

Revision ID: a3c9d1e7b452
Revises: 1f15deacf62a
Create Date: 2026-09-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3c9d1e7b452'
down_revision = '1f15deacf62a'
branch_labels = None
depends_on = None


# Email хранится в нижнем регистре: GET /clients?email=... нормализует ввод
# через .strip().lower() (app/api/clients.py), так что "Demo@email.com" из
# ТЗ находится и при вводе с заглавной, а строка с заглавной буквой не нашлась бы.
DEMO_EMAIL = "demo@email.com"


def upgrade() -> None:
    # Идемпотентно: на БД, где такой клиент/машина уже есть, ничего не
    # дублируется и не перезаписывается.
    op.execute(
        sa.text(
            "INSERT INTO clients (email, name) VALUES (:email, 'Demo Client') "
            "ON CONFLICT (email) DO NOTHING"
        ).bindparams(email=DEMO_EMAIL)
    )
    op.execute(
        sa.text(
            "INSERT INTO cars (client_id, make, model, mileage, last_service_date) "
            "SELECT c.id, 'Hyundai', 'Creta', 80000, DATE '2026-03-01' "
            "FROM clients c WHERE c.email = :email "
            "AND NOT EXISTS (SELECT 1 FROM cars x WHERE x.client_id = c.id "
            "AND x.make = 'Hyundai' AND x.model = 'Creta')"
        ).bindparams(email=DEMO_EMAIL)
    )


def downgrade() -> None:
    # Удаляет только если демо-клиент не успел обзавестись заявками — иначе
    # FK на bookings не даст, да и терять чужую историю здесь не нужно.
    op.execute(
        sa.text(
            "DELETE FROM cars WHERE client_id IN (SELECT id FROM clients WHERE email = :email "
            "AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.client_id = clients.id))"
        ).bindparams(email=DEMO_EMAIL)
    )
    op.execute(
        sa.text(
            "DELETE FROM clients WHERE email = :email "
            "AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.client_id = clients.id) "
            "AND NOT EXISTS (SELECT 1 FROM cars x WHERE x.client_id = clients.id)"
        ).bindparams(email=DEMO_EMAIL)
    )
