import { useEffect, useState } from "react";

import { ClockIcon } from "./icons";
import { formatRemaining, formatUntil } from "./countdownFormat";

// Обратный отсчёт до автоматического завершения этапа "на посту"
// (UI_description.md, п.11: "таймер до завершения работ должно отображаться
// и у сервиса и у клиента"). `targetIso` — это `service_ends_at` заявки,
// та же точка времени, на которую в момент приёма на пост был поставлен
// автотаймер (app/services/robot_timer.py) — не собственная оценка
// фронтенда, а зеркало реального серверного таймера. Форматирование
// (formatRemaining/formatUntil) — в countdownFormat.ts, отдельно от
// компонентов (react-refresh/only-export-components).

// C3 (2026-09-15, доделано по просьбе пользователя — "живая трансляция
// прогресса на посту"): `startedIso` — момент начала ТЕКУЩЕГО раунда работы
// (`Booking.on_post_started_at`, своя точка отсчёта для основной услуги и
// для каждого нового раунда доп. работы — см. app/services/robot_timer.py).
// Процент считается на лету из двух готовых точек времени, без отдельного
// SSE-потока "тиков прогресса" — тикает раз в секунду вместе с самим
// обратным отсчётом.
export function Countdown({ targetIso, startedIso }: { targetIso: string; startedIso?: string | null }) {
  const [remaining, setRemaining] = useState(() => new Date(targetIso).getTime() - Date.now());

  useEffect(() => {
    const tick = () => setRemaining(new Date(targetIso).getTime() - Date.now());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetIso]);

  const progress = (() => {
    if (!startedIso) return null;
    const total = new Date(targetIso).getTime() - new Date(startedIso).getTime();
    if (total <= 0) return null;
    const elapsed = total - remaining;
    return Math.min(100, Math.max(0, Math.round((elapsed / total) * 100)));
  })();

  return (
    <span className="countdown-badge" title="Осталось до автоматического завершения этапа">
      <span className="countdown-badge__row">
        <ClockIcon />
        {remaining > 0 ? formatRemaining(remaining) : "завершается…"}
      </span>
      {progress !== null && (
        <span className="countdown-progress" title={`Выполнено ${progress}%`}>
          <span className="countdown-progress__bar" style={{ width: `${progress}%` }} />
        </span>
      )}
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
      <span className="countdown-badge__row">
        <ClockIcon />
        {formatUntil(remaining)}
      </span>
    </span>
  );
}
