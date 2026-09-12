import { useEffect, useState } from "react";

import { listServices, type Service } from "../api/client";
import { useBookingEvents } from "../api/events";
import { EventLog } from "../components/EventLog";

export function BookingPage() {
  const [services, setServices] = useState<Service[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const events = useBookingEvents();

  useEffect(() => {
    listServices()
      .then(setServices)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div>
      <h1>Запись на обслуживание</h1>
      <p style={{ color: "#666" }}>
        Здесь будет форма записи (шаг A8: выбор услуг → свободный слот → подтверждение).
        Пока — каркас страницы и подключение к API: ниже реальный список услуг из каталога
        станции.
      </p>

      <h2>Каталог услуг</h2>
      {error && <p style={{ color: "red" }}>Ошибка: {error}</p>}
      {!error && services === null && <p>Загрузка...</p>}
      {services && services.length === 0 && <p>Каталог пуст.</p>}
      {services && services.length > 0 && (
        <ul>
          {services.map((service) => (
            <li key={service.id}>
              {service.name} — {service.duration_minutes} мин, {service.price} ₽
            </li>
          ))}
        </ul>
      )}

      <EventLog events={events} />
    </div>
  );
}
