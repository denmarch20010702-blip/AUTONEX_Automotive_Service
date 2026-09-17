from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    additional_works,
    bookings,
    cars,
    catalog,
    clients,
    events,
    health,
    station,
    tire_sets,
)
from app.services.overdue_bookings import schedule_overdue_sweep
from app.services.reminders import schedule_reminder_sweep
from app.services.robot_timer import schedule_stalled_on_post_sweep, scheduler
from app.services.tire_season_reminders import schedule_tire_season_sweep


@asynccontextmanager
async def lifespan(app: FastAPI):
    schedule_reminder_sweep(scheduler)
    schedule_overdue_sweep(scheduler)
    schedule_tire_season_sweep(scheduler)
    # Найдено на практике (2026-09-17, аудит проекта): job конкретного заезда
    # (`schedule_auto_advance`) живёт только в памяти — перезапуск backend'а
    # во время `on_post` теряет его безвозвратно. Этот sweep "дособирает"
    # такие заявки (см. robot_timer.py) — тот же приём, что и overdue_bookings.
    schedule_stalled_on_post_sweep(scheduler)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Станция техобслуживания", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(clients.router)
app.include_router(cars.router)
app.include_router(catalog.router)
app.include_router(bookings.router)
app.include_router(events.router)
app.include_router(station.router)
app.include_router(tire_sets.router)
app.include_router(additional_works.router)
