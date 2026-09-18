import type { Booking } from "../../api/client";

// Вынесено из PostsBoard.tsx (2026-09-18) — см. api/eventsContext.ts за тем
// же приёмом и объяснением (react-refresh/only-export-components). Заодно
// эта чистая функция дешевле тестировать напрямую (D2), чем рендерить весь
// борд — она уже один раз содержала реальный найденный баг ("Далее:" не
// показывалось, см. комментарий ниже).

// "Скоро" — ближайшая по времени принятая (accepted) запись на этот пост
// начинается в пределах NEAR_FUTURE_MS; более дальние по времени записи не
// делают физически свободный сейчас пост "занятым" на вид.
const NEAR_FUTURE_MS = 2 * 60 * 60 * 1000; // 2 часа

export type PostState = "free" | "reserved" | "busy";

export function statusOf(
  bookings: Booking[],
  postId: number,
): { state: PostState; hint: string; booking?: Booking; next?: Booking } {
  const onThisPost = bookings.filter((b) => b.post_id === postId);

  const upcoming = onThisPost
    .filter((b) => b.status === "accepted")
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())[0];
  const upcomingSoon =
    upcoming && new Date(upcoming.start_at).getTime() - Date.now() <= NEAR_FUTURE_MS
      ? upcoming
      : undefined;

  const active = onThisPost.find((b) => b.status === "on_post");
  if (active) {
    // Найдено пользователем на практике (2026-09-16): если следующая
    // запись уже принята на ТОТ ЖЕ пост, где прямо сейчас работает другая
    // машина, очередь была совсем не видна — пост просто выглядел "занят",
    // без намёка, что кто-то уже ждёт следом. Красный (занятость) остаётся
    // главным состоянием, но теперь показываем и "следующего в очереди".
    return { state: "busy", hint: "Машина в работе", booking: active, next: upcomingSoon };
  }

  if (upcomingSoon) {
    return { state: "reserved", hint: "Скоро приедет машина", booking: upcomingSoon };
  }

  return { state: "free", hint: "Свободен" };
}
