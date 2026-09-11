"""seed default posts

Revision ID: dfe1c685b738
Revises: c1528f5a8b01
Create Date: 2026-09-11 18:04:54.189097

"""
from alembic import op
import sqlalchemy as sa


revision = 'dfe1c685b738'
down_revision = 'c1528f5a8b01'
branch_labels = None
depends_on = None


POST_NAMES = ["Пост 1", "Пост 2", "Пост 3"]


def upgrade() -> None:
    # По buisness/buisness.md (AUTONEX) — один филиал с 3 сервисными постами
    # полного цикла. Посты не управляются через CRUD в этом объёме проекта,
    # это фиксированная физическая конфигурация станции.
    posts = sa.table("posts", sa.column("name", sa.String))
    op.bulk_insert(posts, [{"name": name} for name in POST_NAMES])


def downgrade() -> None:
    posts = sa.table("posts", sa.column("name", sa.String))
    op.execute(posts.delete().where(posts.c.name.in_(POST_NAMES)))
