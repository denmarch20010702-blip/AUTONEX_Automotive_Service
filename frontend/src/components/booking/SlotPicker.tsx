import type { SlotOption } from "../../api/client";

// Границы "утро/день/вечер/ночь" — заданы пользователем в
// buisness/UI_description.md: утро 04:00-10:00, день 10:01-16:00,
// вечер 16:01-22:00, ночь 22:01-04:00 (переходит через полночь).
// "to" не включается (< to), поэтому границы заданы как 10/16/22/4 —
// час "10:00" ещё входит в "утро", а "10:01" уже в "день" с точностью до
// используемой сетки слотов в 15 минут.
function bucketForHour(hour: number): string {
  if (hour >= 4 && hour < 10) return "Утро";
  if (hour >= 10 && hour < 16) return "День";
  if (hour >= 16 && hour < 22) return "Вечер";
  return "Ночь"; // 22:00-23:59 и 00:00-03:59
}

const BUCKET_ORDER = ["Утро", "День", "Вечер", "Ночь"];

export function formatSlotLabel(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm}.${d.getFullYear()} - ${hh}:${min}`;
}

export function SlotPicker({
  date,
  onDateChange,
  slots,
  selected,
  onSelect,
  loading,
}: {
  date: string;
  onDateChange: (date: string) => void;
  slots: SlotOption[];
  selected: SlotOption | null;
  onSelect: (slot: SlotOption) => void;
  loading: boolean;
}) {
  return (
    <div>
      <div className="form-field" style={{ maxWidth: 220, margin: "0 auto 1.5rem" }}>
        <label htmlFor="slot-date">Дата</label>
        <input
          id="slot-date"
          type="date"
          value={date}
          onChange={(event) => onDateChange(event.target.value)}
        />
      </div>

      {loading && <p style={{ textAlign: "center" }}>Загрузка слотов...</p>}
      {!loading && slots.length === 0 && (
        <p style={{ textAlign: "center", color: "var(--color-muted)" }}>
          На эту дату свободных слотов нет — попробуй другой день.
        </p>
      )}

      {BUCKET_ORDER.map((label) => {
        const bucketSlots = slots.filter(
          (slot) => bucketForHour(new Date(slot.start_at).getHours()) === label,
        );
        if (bucketSlots.length === 0) return null;
        return (
          <div className="slot-section" key={label}>
            <h3>{label}</h3>
            <div className="slot-grid">
              {bucketSlots.map((slot) => (
                <button
                  key={slot.start_at}
                  type="button"
                  className={`slot-button${selected?.start_at === slot.start_at ? " selected" : ""}`}
                  onClick={() => onSelect(slot)}
                >
                  {formatSlotLabel(slot.start_at)}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
