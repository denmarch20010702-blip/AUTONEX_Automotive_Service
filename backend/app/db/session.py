from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

# NullPool: не переиспользовать asyncpg-соединения между запросами. Обычный пул
# привязывает соединение к event loop'у, в котором оно было открыто — в проде
# loop один и это не проблема, но тестовый раннер (pytest-asyncio) создаёт
# новый event loop под каждый тест, и переиспользование соединения из
# "чужого" loop ломается с ошибками вида "another operation is in progress".
engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
