import type { Booking } from "../../api/client";

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

function statusOf(bookings: Booking[], postId: number): { state: PostState; hint: string } {
  const onThisPost = bookings.filter((b) => b.post_id === postId);

  if (onThisPost.some((b) => b.status === "on_post")) {
    return { state: "busy", hint: "Машина в работе" };
  }

  const upcoming = onThisPost
    .filter((b) => b.status === "accepted")
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())[0];

  if (upcoming) {
    const msUntil = new Date(upcoming.start_at).getTime() - Date.now();
    if (msUntil <= NEAR_FUTURE_MS) {
      return { state: "reserved", hint: "Скоро приедет машина" };
    }
  }

  return { state: "free", hint: "Свободен" };
}

export function PostsBoard({ bookings }: { bookings: Booking[] }) {
  return (
    <div className="posts-board">
      {POSTS.map((post) => {
        const { state, hint } = statusOf(bookings, post.id);
        return (
          <div key={post.id} className={`post-slot post-slot--${state}`} title={hint}>
            <span className="post-slot__label">{post.label}</span>
            <span className="post-slot__hint">{hint}</span>
          </div>
        );
      })}
    </div>
  );
}
