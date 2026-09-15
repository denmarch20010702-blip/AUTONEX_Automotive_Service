// UI_description.md п.33/34: длительность услуги нужно и вводить, и
// показывать не только в минутах, но и в часах — `duration_minutes` в
// данных остаётся как есть (backend ничего не знает про часы), это чисто
// форматирование на фронтенде.
export function formatDuration(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes} мин`;
  if (minutes === 0) return `${hours} ч`;
  return `${hours} ч ${minutes} мин`;
}

export function toTotalMinutes(hours: string, minutes: string): number {
  return (Number(hours) || 0) * 60 + (Number(minutes) || 0);
}

export function splitMinutes(totalMinutes: number): { hours: string; minutes: string } {
  return {
    hours: String(Math.floor(totalMinutes / 60)),
    minutes: String(totalMinutes % 60),
  };
}
