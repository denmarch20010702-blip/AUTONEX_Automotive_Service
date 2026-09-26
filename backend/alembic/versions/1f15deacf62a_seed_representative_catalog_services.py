"""seed representative catalog services

Revision ID: 1f15deacf62a
Revises: f1cddf6c7e48
Create Date: 2026-09-19 19:07:55.314110

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert


revision = '1f15deacf62a'
down_revision = 'f1cddf6c7e48'
branch_labels = None
depends_on = None


SEED_SERVICES = [
    # Задание 12, "Должен включать": "Каталог услуг: ТО по регламенту, замена
    # шин, замена масла и подобное" — буквальные примеры из условия. Раньше
    # каталог на свежей БД был пуст (кроме 2 защищённых проводников к
    # хранению шин, не обычных услуг), и проверяющий видел пустой список,
    # пока не добавит услуги сам или не прогонит скрипты-доказательства.
    # Название "Плановое ТО" намеренно содержит ключевое слово "ТО" — тот же
    # паттерн, что матчит rule-based ИИ-диагностика (см. ai_diagnostics.py) —
    # чтобы предложение доп. работ было видно сразу, без специальной настройки.
    ("Плановое ТО", 90, "4500.00"),
    ("Замена масла", 30, "1800.00"),
    ("Замена шин", 40, "1600.00"),
    ("Замена тормозных колодок", 45, "2500.00"),
    ("Диагностика подвески", 30, "1200.00"),
]


def upgrade() -> None:
    # `ON CONFLICT (name) DO NOTHING`, а не `op.bulk_insert` — на живой БД
    # уже мог накопиться каталог с частью этих же названий (ручное
    # тестирование станции); эта миграция не должна падать или дублировать
    # строки нигде, где что-то из списка уже есть.
    services = sa.table(
        "services",
        sa.column("name", sa.String),
        sa.column("duration_minutes", sa.Integer),
        sa.column("price", sa.Numeric),
        sa.column("protected", sa.Boolean),
    )
    for name, duration_minutes, price in SEED_SERVICES:
        op.execute(
            pg_insert(services)
            .values(name=name, duration_minutes=duration_minutes, price=price, protected=False)
            .on_conflict_do_nothing(index_elements=["name"])
        )


def downgrade() -> None:
    services = sa.table("services", sa.column("name", sa.String))
    op.execute(
        services.delete().where(services.c.name.in_([name for name, _, _ in SEED_SERVICES]))
    )
