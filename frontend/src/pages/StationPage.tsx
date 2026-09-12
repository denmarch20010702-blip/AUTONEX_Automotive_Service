import { useCallback, useEffect, useState } from "react";

import { listBookings, type Booking } from "../api/client";
import { useBookingEvents } from "../api/events";
import { EventLog } from "../components/EventLog";

export function StationPage() {
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const events = useBookingEvents();

  const reload = useCallback(() => {
    listBookings()
      .then(setBookings)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // Пока перезапрашиваем список по каждому событию, а не редактируем его на
  // лету — просто и достаточно для каркаса; B7 (полноценный экран станции
  // по постам) сделает это аккуратнее.
  useEffect(() => {
    if (events.length > 0) reload();
  }, [events, reload]);

  return (
    <div>
      <h1>Экран станции</h1>
      <p style={{ color: "#666" }}>
        Здесь будет полноценная доска заявок по постам (шаг B7). Пока — каркас страницы,
        подключение к API и живое обновление списка по событиям из A6.
      </p>

      <h2>Все заявки</h2>
      {error && <p style={{ color: "red" }}>Ошибка: {error}</p>}
      {!error && bookings === null && <p>Загрузка...</p>}
      {bookings && bookings.length === 0 && <p>Заявок пока нет.</p>}
      {bookings && bookings.length > 0 && (
        <table border={1} cellPadding={6} style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th>ID</th>
              <th>Пост</th>
              <th>Начало</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {bookings.map((booking) => (
              <tr key={booking.id}>
                <td>{booking.id}</td>
                <td>{booking.post_id}</td>
                <td>{new Date(booking.start_at).toLocaleString()}</td>
                <td>{booking.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <EventLog events={events} />
    </div>
  );
}
