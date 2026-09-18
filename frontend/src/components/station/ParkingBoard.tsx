import type { Booking, ParkingSpot } from "../../api/client";

// buisness.md (C7, "Smart Parking Management", 2026-09-17): 6 фиксированных
// мест ожидания — тот же принцип индикации, что и у PostsBoard.tsx, только
// прямоугольники меньше и мест больше (6 вместо 3). Место занято ДО
// обслуживания (клиент подтвердил приезд, ждёт своего start_at — оранжевый,
// как "reserved" у постов) либо ПОСЛЕ (заявка готова, ждёт, чтобы забрали —
// красный, как "busy" у постов, потому что именно это состояние копит
// наценку за простой сверх бесплатных 2 часов).
type SpotState = "free" | "waiting" | "ready";

function stateOf(bookings: Booking[], spotId: number): { state: SpotState; booking?: Booking } {
  const occupying = bookings.find((b) => b.parking_spot_id === spotId);
  if (!occupying) return { state: "free" };
  return { state: occupying.status === "ready" ? "ready" : "waiting", booking: occupying };
}

export function ParkingBoard({ spots, bookings }: { spots: ParkingSpot[]; bookings: Booking[] }) {
  if (spots.length === 0) return <div className="parking-board" />;

  return (
    <div className="parking-board">
      {spots.map((spot) => {
        const { state, booking } = stateOf(bookings, spot.id);
        const hint =
          state === "free"
            ? "Свободно"
            : state === "waiting"
              ? "Машина ждёт начала обслуживания"
              : "Готова — ждёт, когда забрать";
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
