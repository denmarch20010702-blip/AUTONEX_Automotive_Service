import type { Booking, ParkingSpot } from "../../api/client";

// Вынесено из ParkingBoard.tsx (2026-09-18) — см. api/eventsContext.ts за
// тем же приёмом и объяснением (react-refresh/only-export-components).
//
// UI_description.md п.52 (2026-09-18, найдено пользователем на практике):
// раньше "занято до обслуживания" красилось оранжевым, а "занято после" —
// красным, что путало с "зарезервировано" у постов. Единая схема, как у
// PostsBoard.tsx: зелёный — свободно, оранжевый — зарезервировано (места
// физически ещё нет, но оно уже отложено под машину, которая скоро его
// попросит — см. п.51, `assign_parking_spot`), красный — занято (машина
// физически стоит, независимо от фазы — до или после обслуживания).
export type SpotState = "free" | "reserved" | "occupied";

export interface SpotStatus {
  state: SpotState;
  booking?: Booking;
}

export function computeSpotStates(spots: ParkingSpot[], bookings: Booking[]): Map<number, SpotStatus> {
  const occupiedBySpot = new Map<number, Booking>();
  for (const b of bookings) {
    if (b.parking_spot_id != null) occupiedBySpot.set(b.parking_spot_id, b);
  }
  // Тот же расчёт резерва, что и на backend'е (parking.py::assign_parking_
  // spot, п.51) — по одному месту на каждую заявку, реально сейчас в работе
  // на посту. Это количество, не конкретное место — помечаем им первые N
  // свободных мест по id (тот же порядок, в котором backend их выбирает).
  const reservedCount = bookings.filter((b) => b.status === "on_post").length;
  const freeSpots = spots.filter((s) => !occupiedBySpot.has(s.id));
  const reservedIds = new Set(freeSpots.slice(0, reservedCount).map((s) => s.id));

  const result = new Map<number, SpotStatus>();
  for (const spot of spots) {
    const booking = occupiedBySpot.get(spot.id);
    if (booking) {
      result.set(spot.id, { state: "occupied", booking });
    } else if (reservedIds.has(spot.id)) {
      result.set(spot.id, { state: "reserved" });
    } else {
      result.set(spot.id, { state: "free" });
    }
  }
  return result;
}
