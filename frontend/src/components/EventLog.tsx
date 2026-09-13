import type { BookingEvent } from "../api/events";

const LABELS: Record<BookingEvent["type"], string> = {
  booking_created: "Новая заявка",
  booking_status_changed: "Статус изменился",
  additional_work_proposed: "Предложена доп. работа",
  additional_work_responded: "Ответ по доп. работе",
};

export function EventLog({ events }: { events: BookingEvent[] }) {
  return (
    <section style={{ marginTop: "2rem" }}>
      <h2>Живые события (realtime, A6)</h2>
      <p style={{ color: "#666" }}>
        Обновляется само, без перезагрузки страницы — открой эту страницу ещё в одной
        вкладке и создай заявку через{" "}
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
          Swagger
        </a>
        , чтобы увидеть.
      </p>
      {events.length === 0 ? (
        <p>Пока событий не было.</p>
      ) : (
        <ul>
          {events.map((event, index) => (
            <li key={index}>
              <code>{event.receivedAt}</code> — {LABELS[event.type]}:{" "}
              {event.type.startsWith("additional_work") ? "доп. работа" : "заявка"} #
              {String(event.data.id)}, статус <b>{String(event.data.status)}</b>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
