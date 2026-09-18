// Вынесено из SlotPicker.tsx (2026-09-18) — см. api/eventsContext.ts за тем
// же приёмом и объяснением (react-refresh/only-export-components).
export function formatSlotLabel(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm}.${d.getFullYear()} - ${hh}:${min}`;
}
