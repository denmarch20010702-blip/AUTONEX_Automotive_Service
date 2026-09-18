// Вынесено из Countdown.tsx (2026-09-18) — см. api/eventsContext.ts за тем
// же приёмом (react-refresh/only-export-components: файл ниже экспортирует
// два компонента, чистым функциям тут не место).

// Найденный пользователем на практике реальный баг (2026-09-18): для долгой
// услуги (или продлённого доп. работой раунда) обратный отсчёт показывал
// голые минуты без пересчёта в часы — например "1426:33" вместо "23:46:33",
// что выглядело как нечитаемое число минут, а не таймер.
export function formatRemaining(ms: number): string {
  if (ms <= 0) return "00:00";
  const totalSeconds = Math.floor(ms / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const hh = String(hours).padStart(2, "0");
  const mm = String(minutes).padStart(2, "0");
  const ss = String(seconds).padStart(2, "0");
  if (days > 0) return `${days}д ${hh}:${mm}:${ss}`;
  if (hours > 0) return `${hh}:${mm}:${ss}`;
  return `${mm}:${ss}`;
}

// Отсчёт до НАЧАЛА записи (не до конца работ) — по прямой просьбе
// пользователя (2026-09-14), после того как выяснилось, что принять машину
// на пост раньше назначенного времени теперь честно запрещено (реальный
// найденный баг): станция и клиент должны видеть, сколько ещё осталось
// ждать, а не только то, что "пока рано". Формат покрывает диапазон от
// дней до секунд — записи бывают и на завтра, и на следующей неделе.
export function formatUntil(ms: number): string {
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
