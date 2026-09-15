import { useEffect, useState } from "react";

import { ClockIcon } from "./icons";

// Обратный отсчёт до автоматического завершения этапа "на посту"
// (UI_description.md, п.11: "таймер до завершения работ должно отображаться
// и у сервиса и у клиента"). `targetIso` — это `service_ends_at` заявки,
// та же точка времени, на которую в момент приёма на пост был поставлен
// автотаймер (app/services/robot_timer.py) — не собственная оценка
// фронтенда, а зеркало реального серверного таймера.
function formatRemaining(ms: number): string {
  if (ms <= 0) return "00:00";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

// Отсчёт до НАЧАЛА записи (не до конца работ) — по прямой просьбе
// пользователя (2026-09-14), после того как выяснилось, что принять машину
// на пост раньше назначенного времени теперь честно запрещено (реальный
// найденный баг): станция и клиент должны видеть, сколько ещё осталось
// ждать, а не только то, что "пока рано". Формат покрывает диапазон от
// дней до секунд — записи бывают и на завтра, и на следующей неделе.
function formatUntil(ms: number): string {
  if (ms <= 0) return "уже наступило";
  const totalMinutes = Math.floor(ms / 60000);
  const days = Math.floor(totalMinutes / (24 * 60));
  const hours = Math.floor((totalMinutes % (24 * 60)) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `${days} дн ${hours} ч`;
  if (hours > 0) return `${hours} ч ${minutes} мин`;
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${minutes} мин ${String(seconds).padStart(2, "0")} с`;
}

export function Countdown({ targetIso }: { targetIso: string }) {
  const [remaining, setRemaining] = useState(() => new Date(targetIso).getTime() - Date.now());

  useEffect(() => {
    const tick = () => setRemaining(new Date(targetIso).getTime() - Date.now());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetIso]);

  return (
    <span className="countdown-badge" title="Осталось до автоматического завершения этапа">
      <ClockIcon />
      {remaining > 0 ? formatRemaining(remaining) : "завершается…"}
    </span>
  );
}

// UI_description.md (2026-09-14): таймер "до начала записи" — рядом с
// заявками, назначенными на будущее (статус "принята", start_at ещё не
// наступил), и у станции, и у клиента. Отдельный компонент, а не вариант
// `Countdown` выше — другой формат (дни/часы, не только мм:сс) и другой
// смысл (ждём НАЧАЛА, не конца работ).
export function UpcomingCountdown({ targetIso }: { targetIso: string }) {
  const [remaining, setRemaining] = useState(() => new Date(targetIso).getTime() - Date.now());

  useEffect(() => {
    const tick = () => setRemaining(new Date(targetIso).getTime() - Date.now());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetIso]);

  return (
    <span className="countdown-badge" title="Осталось до назначенного времени записи">
      <ClockIcon />
      {formatUntil(remaining)}
    </span>
  );
}
