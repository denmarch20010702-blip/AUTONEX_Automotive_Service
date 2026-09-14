import { useEffect, useState } from "react";

import { getAvailableSlots, rescheduleBooking, type Booking, type SlotOption } from "../../api/client";
import { formatSlotLabel } from "./SlotPicker";

function todayIso(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftDate(dateStr: string, deltaDays: number): string {
  const [year, month, day] = dateStr.split("-").map(Number);
  const d = new Date(year, month - 1, day);
  d.setDate(d.getDate() + deltaDays);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

// B4 (перенос записи) — компактный виджет прямо в строке таблицы "Мои
// записи": та же логика выбора слота, что и в мастере записи (SlotPicker),
// но без вынесенных на края экрана стрелок — здесь это неуместно, виджет
// открывается внутри таблицы, а не на весь экран.
export function RescheduleControl({
  booking,
  onRescheduled,
  onError,
}: {
  booking: Booking;
  onRescheduled: () => void;
  onError: (message: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(todayIso());
  const [slots, setSlots] = useState<SlotOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getAvailableSlots(booking.services.map((s) => s.id), date, booking.id)
      .then(setSlots)
      .catch((err) => onError((err as Error).message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, date, booking.id]);

  const confirm = async (slot: SlotOption) => {
    setBusy(true);
    try {
      await rescheduleBooking(booking.id, slot.start_at);
      setOpen(false);
      onRescheduled();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (booking.status !== "accepted") return null;

  if (!open) {
    return (
      <button type="button" className="ghost-button" onClick={() => setOpen(true)}>
        Перенести
      </button>
    );
  }

  return (
    <div style={{ minWidth: 220 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.4rem" }}>
        <button type="button" className="ghost-button" onClick={() => setDate((d) => shiftDate(d, -1))}>
          ‹
        </button>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} style={{ flex: 1 }} />
        <button type="button" className="ghost-button" onClick={() => setDate((d) => shiftDate(d, 1))}>
          ›
        </button>
      </div>
      {loading && <p className="panel-empty">Загрузка слотов...</p>}
      {!loading && slots.length === 0 && <p className="panel-empty">На эту дату свободных слотов нет.</p>}
      <div className="slot-grid">
        {slots.map((slot) => (
          <button
            key={slot.start_at}
            type="button"
            className="slot-button"
            disabled={busy}
            onClick={() => confirm(slot)}
          >
            {formatSlotLabel(slot.start_at)}
          </button>
        ))}
      </div>
      <button type="button" className="ghost-button" style={{ marginTop: "0.4rem" }} onClick={() => setOpen(false)}>
        Отмена
      </button>
    </div>
  );
}
