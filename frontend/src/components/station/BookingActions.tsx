import { updateBookingStatus, type Booking } from "../../api/client";

const CANCELLABLE = new Set(["accepted", "on_post", "awaiting_approval", "ready"]);

// Кнопки смены статуса заявки на станции — по прямой просьбе пользователя:
// отметить клиента на посту, принять/отклонить согласование доп. работ,
// принять готовую работу в конце (выдать), и в любой момент отменить.
//
// Ограничение: "Согласовано" и "Отклонено" оба ведут в один и тот же статус
// READY — модель AdditionalWork (из A2.1) пока не подключена к этому потоку
// статусов заявки, так что различие сейчас смысловое (для оператора), а не
// сохраняется отдельным полем. Подключение AdditionalWork — за рамками
// этого шага.
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
    buttons.push({ label: "Запросить согласование", status: "awaiting_approval" });
  }
  if (booking.status === "awaiting_approval") {
    buttons.push({
      label: "Согласовано",
      status: "ready",
      title: "Доп. работы одобрены клиентом",
    });
    buttons.push({
      label: "Отклонено",
      status: "ready",
      title: "Клиент отказался от доп. работ — делаем только основную услугу",
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
          className="link-button"
          title={b.title}
          style={b.danger ? { color: "var(--color-danger)" } : undefined}
          onClick={() => act(b.status)}
        >
          {b.label}
        </button>
      ))}
    </div>
  );
}
