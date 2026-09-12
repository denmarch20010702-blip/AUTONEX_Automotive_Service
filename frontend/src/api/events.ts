import { useEffect, useRef, useState } from "react";

import { API_URL } from "./client";

export interface BookingEvent {
  type: "booking_created" | "booking_status_changed";
  data: Record<string, unknown>;
  receivedAt: string;
}

const MAX_EVENTS = 20;

// Подписка на тот же /events, что уже проверен вручную через `curl -N`
// (см. VERIFICATION.md) — здесь то же самое, но через встроенный в браузер
// EventSource вместо curl. Один хук на всё приложение (см. App.tsx),
// чтобы обе страницы видели одни и те же события без повторного подключения.
export function useBookingEvents(): BookingEvent[] {
  const [events, setEvents] = useState<BookingEvent[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const source = new EventSource(`${API_URL}/events`);
    sourceRef.current = source;

    const handle = (type: BookingEvent["type"]) => (message: MessageEvent<string>) => {
      const event: BookingEvent = {
        type,
        data: JSON.parse(message.data),
        receivedAt: new Date().toLocaleTimeString(),
      };
      setEvents((prev) => [event, ...prev].slice(0, MAX_EVENTS));
    };

    source.addEventListener("booking_created", handle("booking_created"));
    source.addEventListener("booking_status_changed", handle("booking_status_changed"));

    return () => source.close();
  }, []);

  return events;
}

// Живой статус конкретной заявки — используется на клиентском экране
// успеха, чтобы клиент видел, как его заявку обрабатывают на станции, без
// перезагрузки страницы (buisness/UI_description.md: "такой же индикатор
// и статус отслеживания заявки добавить клиенту").
export function useBookingStatus(bookingId: number, initialStatus: string): string {
  const events = useBookingEvents();
  const latest = events.find(
    (event) => event.type === "booking_status_changed" && event.data.id === bookingId,
  );
  return (latest?.data.status as string | undefined) ?? initialStatus;
}
