import type { Booking, ParkingSpot } from "../../api/client";
import { computeSpotStates } from "./parkingSpotStatus";

// buisness.md (C7, "Smart Parking Management", 2026-09-17): 6 фиксированных
// мест ожидания — тот же принцип индикации, что и у PostsBoard.tsx, только
// прямоугольники меньше и мест больше (6 вместо 3). Место занято ДО
// обслуживания (клиент подтвердил приезд, ждёт своего start_at) либо ПОСЛЕ
// (заявка готова, ждёт, чтобы забрали) — обе фазы теперь красные (см.
// parkingSpotStatus.ts, п.52), оранжевый переиспользован под "зарезервировано"
// (п.51), как у постов.

export function ParkingBoard({ spots, bookings }: { spots: ParkingSpot[]; bookings: Booking[] }) {
  if (spots.length === 0) return <div className="parking-board" />;

  const states = computeSpotStates(spots, bookings);

  return (
    <div className="parking-board">
      {spots.map((spot) => {
        const { state, booking } = states.get(spot.id) ?? { state: "free" as const };
        const hint =
          state === "free"
            ? "Свободно"
            : state === "reserved"
              ? "Зарезервировано для машины, которая скоро закончит обслуживание"
              : "Занято";
        return (
          <div key={spot.id} className={`parking-spot parking-spot--${state}`} title={`${spot.name}: ${hint}`}>
            <span className="parking-spot__label">{spot.name.replace("Место ", "")}</span>
            {booking && <span className="parking-spot__hint">№{booking.id}</span>}
          </div>
        );
      })}
    </div>
  );
}
