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
