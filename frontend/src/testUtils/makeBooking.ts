import type { Booking } from "../api/client";

let nextId = 1;

// Общий фабричный хелпер для тестов (D2, 2026-09-18) — заполняет все
// обязательные поля `Booking` разумными дефолтами, тест переопределяет
// только то, что ему важно.
export function makeBooking(overrides: Partial<Booking> = {}): Booking {
  const id = nextId++;
  return {
    id,
    client_id: 1,
    car_id: 1,
    post_id: 1,
    start_at: new Date().toISOString(),
    end_at: new Date().toISOString(),
    status: "accepted",
    service_ends_at: null,
    on_post_started_at: null,
    services: [],
    tire_offer_declined: false,
    parking_spot_id: null,
    parked_at: null,
    ...overrides,
  };
}
