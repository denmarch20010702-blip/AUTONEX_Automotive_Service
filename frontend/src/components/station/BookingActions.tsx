import { updateBookingStatus, type Booking } from "../../api/client";

const CANCELLABLE = new Set(["accepted", "on_post", "awaiting_approval", "ready"]);

// Кнопки смены статуса заявки на станции: отметить клиента на посту,
// принять готовую работу (выдать), в любой момент отменить.
//
// Заметка пользователя (UI_description.md, п.13, 2026-09-13): раньше здесь
// были ещё "Запросить согласование"/"Согласовано"/"Отклонено" — фиктивные
// кнопки, никак не связанные с реальными AdditionalWork (просто трогали
// статус заявки). Согласование теперь по-настоящему делает клиент в своём
// кабинете (B2), а заявка сама переходит в "готова", как только клиент
// ответил на последнее предложение (см. app/api/additional_works.py) — или
// автоматически по таймеру (app/services/robot_timer.py). Ручной кнопки для
// входа в "ожидает согласования" больше нет — в этот статус заявка попадает
// только когда есть реальное неотвеченное предложение.
export function BookingActions({
  booking,
  onChanged,
  onError,
}: {
  booking: Booking;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const act = async (status: string) => {
    try {
      await updateBookingStatus(booking.id, status);
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    }
  };

  const buttons: Array<{ label: string; status: string; danger?: boolean; title?: string }> = [];

  if (booking.status === "accepted") {
    buttons.push({ label: "Принять на пост", status: "on_post" });
  }
  if (booking.status === "on_post") {
    buttons.push({ label: "Готово", status: "ready" });
  }
  if (booking.status === "awaiting_approval") {
    buttons.push({
      label: "Готово",
      status: "ready",
      title: "Обычно происходит само, как только клиент ответит на предложение — эта кнопка на случай сбоя",
    });
  }
  if (booking.status === "ready") {
    buttons.push({ label: "Выдать", status: "issued", title: "Полное завершение — заявка исчезнет из списка" });
  }
  if (CANCELLABLE.has(booking.status)) {
    buttons.push({ label: "Отменить", status: "cancelled", danger: true });
  }

  if (buttons.length === 0) return null;

  return (
    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
      {buttons.map((b) => (
        <button
          key={b.label}
          type="button"
          className={`action-button${b.danger ? " danger" : ""}`}
          title={b.title}
          onClick={() => act(b.status)}
        >
          {b.label}
        </button>
      ))}
    </div>
  );
}
