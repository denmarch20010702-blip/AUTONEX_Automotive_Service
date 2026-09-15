import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { API_URL } from "./client";

export interface BookingEvent {
  type:
    | "booking_created"
    | "booking_status_changed"
    | "booking_rescheduled"
    | "additional_work_proposed"
    | "additional_work_responded";
  data: Record<string, unknown>;
  receivedAt: string;
}

const MAX_EVENTS = 20;

function useBookingEventsSource(): BookingEvent[] {
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
    source.addEventListener("booking_rescheduled", handle("booking_rescheduled"));
    source.addEventListener("additional_work_proposed", handle("additional_work_proposed"));
    source.addEventListener("additional_work_responded", handle("additional_work_responded"));

    return () => source.close();
  }, []);

  return events;
}

const EventsContext = createContext<BookingEvent[]>([]);

// Подписка на тот же /events, что уже проверен вручную через `curl -N`
// (см. VERIFICATION.md) — один-единственный `EventSource` на всё приложение
// (см. App.tsx), а не по одному на каждую страницу/компонент, которая его
// использует — раньше комментарий обещал это, но по факту `StationPage`,
// `CabinetPage` и `SuccessCard` каждый открывали собственное соединение.
export function EventsProvider({ children }: { children: ReactNode }) {
  const events = useBookingEventsSource();
  return <EventsContext.Provider value={events}>{children}</EventsContext.Provider>;
}

export function useBookingEvents(): BookingEvent[] {
  return useContext(EventsContext);
}

// Найденный на практике реальный баг (2026-09-15, пользователь: "невозможно
// перейти в кабинет станции — не открывался"): StationPage/CabinetPage
// раньше перезапрашивали ВСЕ свои данные (5-8 параллельных запросов на
// страницу, плюс по одному /additional-works НА КАЖДУЮ строку заявки) на
// КАЖДОЕ отдельное SSE-событие без каких-либо задержек. Всплеск из 10-20
// событий подряд (например, серия propose/respond/schedule доп. работ,
// которая сама публикует по событию на каждый шаг) давал сотни запросов за
// секунды — вкладка реально "зависала", пока не успевала их все разгрести.
// Дебаунс коалесцирует любую пачку событий в ОДИН тик после того, как они
// перестали приходить `delayMs` — независимо от того, сколько их было.
export function useDebouncedEventTick(delayMs = 400): number {
  const events = useBookingEvents();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (events.length === 0) return;
    const id = setTimeout(() => setTick((t) => t + 1), delayMs);
    return () => clearTimeout(id);
  }, [events, delayMs]);

  return tick;
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
