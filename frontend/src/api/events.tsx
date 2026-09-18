import { useEffect, useRef, useState, type ReactNode } from "react";

import { API_URL } from "./client";
import { EventsContext, type BookingEvent } from "./eventsContext";

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

// Подписка на тот же /events, что уже проверен вручную через `curl -N`
// (см. VERIFICATION.md) — один-единственный `EventSource` на всё приложение
// (см. App.tsx), а не по одному на каждую страницу/компонент, которая его
// использует — раньше комментарий обещал это, но по факту `StationPage`,
// `CabinetPage` и `SuccessCard` каждый открывали собственное соединение.
//
// Хуки-потребители (`useBookingEvents`/`useDebouncedEventTick`/
// `useBookingStatus`) и сам тип/контекст вынесены в eventHooks.ts/
// eventsContext.ts (2026-09-18) — этот файл теперь экспортирует только
// компонент, как того требует Vite Fast Refresh.
export function EventsProvider({ children }: { children: ReactNode }) {
  const events = useBookingEventsSource();
  return <EventsContext.Provider value={events}>{children}</EventsContext.Provider>;
}
