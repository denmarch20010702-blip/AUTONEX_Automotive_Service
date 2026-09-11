from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import bookings, cars, catalog, clients, health

app = FastAPI(title="Станция техобслуживания")

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
