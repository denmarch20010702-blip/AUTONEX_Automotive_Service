import type { BookingEvent } from "../api/events";

const LABELS: Record<BookingEvent["type"], string> = {
  booking_created: "Новая заявка",
  booking_status_changed: "Статус изменился",
  additional_work_proposed: "Предложена доп. работа",
  additional_work_responded: "Ответ по доп. работе",
};

export function EventLog({ events }: { events: BookingEvent[] }) {
  return (
    <div className="panel" style={{ marginTop: "2rem" }}>
      <div className="panel-header">
        <h2>Живые события (realtime)</h2>
      </div>
      <p className="panel-empty" style={{ marginTop: 0 }}>
        Обновляется само, без перезагрузки страницы.
      </p>
      {events.length === 0 ? (
        <p className="panel-empty">Пока событий не было.</p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
          {events.map((event, index) => (
            <li key={index}>
              <code>{event.receivedAt}</code> — {LABELS[event.type]}:{" "}
              {event.type.startsWith("additional_work") ? "доп. работа" : "заявка"} #
              {String(event.data.id)}, статус <b>{String(event.data.status)}</b>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
