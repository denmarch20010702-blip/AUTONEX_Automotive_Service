from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import async_session
from app.models import (
    AdditionalWork,
    AdditionalWorkStatus,
    Booking,
    BookingStatus,
    Car,
    Client,
    Post,
    ProposedBy,
    Service,
    TireSet,
)


@pytest.mark.asyncio
async def test_schema_roundtrip() -> None:
    async with async_session() as session:
        client = Client(email="test@example.com", name="Тест Тестов")
        post = Post(name="Пост 1")
        service = Service(name="Замена масла", duration_minutes=30, price=Decimal("1500.00"))
        session.add_all([client, post, service])
        await session.flush()

        car = Car(client_id=client.id, make="Toyota", model="Camry", mileage=50000)
        session.add(car)
        await session.flush()

        start = datetime.now(timezone.utc)
        booking = Booking(
            client_id=client.id,
            car_id=car.id,
            post_id=post.id,
            start_at=start,
            end_at=start + timedelta(minutes=service.duration_minutes),
            status=BookingStatus.ACCEPTED,
            services=[service],
        )
        session.add(booking)
        await session.flush()

        tire_set = TireSet(client_id=client.id, car_id=car.id)
        additional_work = AdditionalWork(
            booking_id=booking.id,
            description="Обнаружен износ тормозных колодок",
            price=Decimal("2500.00"),
            proposed_by=ProposedBy.MECHANIC,
            status=AdditionalWorkStatus.PENDING,
        )
        session.add_all([tire_set, additional_work])
        await session.commit()

        booking_id = booking.id
        tire_set_id = tire_set.id
        additional_work_id = additional_work.id

    async with async_session() as session:
        result = await session.execute(select(Booking).where(Booking.id == booking_id))
        loaded = result.scalar_one()
        assert loaded.status == BookingStatus.ACCEPTED
        assert loaded.client_id == client.id
        assert loaded.car_id == car.id

        tire_set_loaded = await session.get(TireSet, tire_set_id)
        assert tire_set_loaded is not None
        assert tire_set_loaded.issued_at is None  # на хранении

        work_loaded = await session.get(AdditionalWork, additional_work_id)
        assert work_loaded is not None
        assert work_loaded.status == AdditionalWorkStatus.PENDING
        assert work_loaded.proposed_by == ProposedBy.MECHANIC

        # уборка за собой, чтобы тест был повторяемым
        for obj in (work_loaded, tire_set_loaded, loaded):
            await session.delete(obj)
        await session.commit()

    async with async_session() as session:
        for model, pk in ((Car, car.id), (Client, client.id), (Post, post.id), (Service, service.id)):
            obj = await session.get(model, pk)
            if obj is not None:
                await session.delete(obj)
        await session.commit()
