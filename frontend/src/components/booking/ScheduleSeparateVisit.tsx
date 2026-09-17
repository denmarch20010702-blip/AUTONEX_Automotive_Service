import { useEffect, useState } from "react";

import { getAvailableSlots, scheduleAdditionalWorks, type SlotOption } from "../../api/client";
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

// UI_description.md п.37 (2026-09-14): когда станция предлагает доп. работу,
// но сразу нет места (пост занят следующей заявкой), клиент выбирает время
// для ОТДЕЛЬНОГО визита именно на эту работу — тот же виджет "мини-
// календарь", что и у переноса записи (RescheduleControl, B4), а не своя
// отдельная реализация выбора даты/слота.
//
// Найдено пользователем на практике (2026-09-17): когда на посту уже
// очередь, КАЖДАЯ доп. работа по отдельности не влезала — клиенту
// приходилось открывать по отдельному мини-календарю на каждую и
// записываться на несколько отдельных визитов. Теперь этот компонент
// принимает СРАЗУ несколько работ (`workIds`/`serviceIds`) — один выбор
// времени создаёт один визит на все услуги разом (см. schedule-batch на
// backend'е, additional_works.py).
export function ScheduleSeparateVisit({
  workIds,
  serviceIds,
  onScheduled,
  onCancel,
  onError,
}: {
  workIds: number[];
  serviceIds: number[];
  onScheduled: () => void;
  onCancel: () => void;
  onError: (message: string) => void;
}) {
  const [date, setDate] = useState(todayIso());
  const [slots, setSlots] = useState<SlotOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const serviceIdsKey = serviceIds.join(",");

  useEffect(() => {
    setLoading(true);
    getAvailableSlots(serviceIds, date)
      .then(setSlots)
      .catch((err) => onError((err as Error).message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, serviceIdsKey]);

  const confirm = async (slot: SlotOption) => {
    setBusy(true);
    try {
      await scheduleAdditionalWorks(workIds, slot.start_at);
      onScheduled();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ minWidth: 220, marginTop: "0.4rem" }}>
      <p className="panel-empty" style={{ margin: "0 0 0.4rem" }}>
        {workIds.length > 1
          ? `Сейчас нет места для ${workIds.length} доп. работ сразу — выберите время ОДНОГО визита на все.`
          : "Сейчас нет места для этой работы — выберите время отдельного визита."}
      </p>
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
      <button type="button" className="ghost-button" style={{ marginTop: "0.4rem" }} onClick={onCancel}>
        Отмена
      </button>
    </div>
  );
}
