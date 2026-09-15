import type { Booking, CarInfo, ClientInfo } from "../../api/client";
import { Countdown, UpcomingCountdown } from "../Countdown";

// Прямая просьба пользователя (2026-09-14): наверху экрана станции — 3
// прямоугольника, обозначающих реальные физические посты (см.
// backend/alembic/versions/dfe1c685b738_seed_default_posts.py — посты не
// управляются через CRUD, это фиксированная конфигурация станции из 3 мест).
// Цвет контура — состояние поста ПРЯМО СЕЙЧАС:
//   зелёный  — пост свободен;
//   оранжевый — на пост скоро приедет машина (запись принята, но ещё не
//               наступило время приёма на пост — п. "исправь баг" выше);
//   красный  — машина сейчас в работе на этом посту.
// "Скоро" — ближайшая по времени принятая (accepted) запись на этот пост
// начинается в пределах NEAR_FUTURE_MS; более дальние по времени записи не
// делают физически свободный сейчас пост "занятым" на вид.
const NEAR_FUTURE_MS = 2 * 60 * 60 * 1000; // 2 часа

const POSTS = [
  { id: 1, label: "Пост 1" },
  { id: 2, label: "Пост 2" },
  { id: 3, label: "Пост 3" },
];

type PostState = "free" | "reserved" | "busy";

function statusOf(
  bookings: Booking[],
  postId: number,
): { state: PostState; hint: string; booking?: Booking } {
  const onThisPost = bookings.filter((b) => b.post_id === postId);

  const active = onThisPost.find((b) => b.status === "on_post");
  if (active) {
    return { state: "busy", hint: "Машина в работе", booking: active };
  }

  const upcoming = onThisPost
    .filter((b) => b.status === "accepted")
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())[0];

  if (upcoming) {
    const msUntil = new Date(upcoming.start_at).getTime() - Date.now();
    if (msUntil <= NEAR_FUTURE_MS) {
      return { state: "reserved", hint: "Скоро приедет машина", booking: upcoming };
    }
  }

  return { state: "free", hint: "Свободен" };
}

// UI_description.md п.42 (2026-09-15): на доске постов должно быть видно,
// чья это машина (имя владельца), какая машина и сколько времени осталось —
// не только цвет контура. Для этого нужны клиенты/машины со станции (те же
// справочники, что уже используются в таблице "Все заявки"), не только
// список заявок.
export function PostsBoard({
  bookings,
  clients,
  cars,
}: {
  bookings: Booking[];
  clients: ClientInfo[];
  cars: CarInfo[];
}) {
  const clientOf = (clientId: number): ClientInfo | undefined => clients.find((c) => c.id === clientId);
  const carOf = (carId: number): CarInfo | undefined => cars.find((c) => c.id === carId);

  return (
    <div className="posts-board">
      {POSTS.map((post) => {
        const { state, hint, booking } = statusOf(bookings, post.id);
        const client = booking ? clientOf(booking.client_id) : undefined;
        const car = booking ? carOf(booking.car_id) : undefined;
        return (
          <div key={post.id} className={`post-slot post-slot--${state}`} title={hint}>
            <span className="post-slot__label">{post.label}</span>
            <span className="post-slot__hint">{hint}</span>
            {booking && (client || car) && (
              <span className="post-slot__details">
                {client && <span className="post-slot__owner">{client.name}</span>}
                {car && (
                  <span className="post-slot__car">
                    {car.make} {car.model}
                  </span>
                )}
              </span>
            )}
            {state === "busy" && booking?.service_ends_at && (
              <Countdown targetIso={booking.service_ends_at} startedIso={booking.on_post_started_at} />
            )}
            {state === "reserved" && booking && <UpcomingCountdown targetIso={booking.start_at} />}
          </div>
        );
      })}
    </div>
  );
}
