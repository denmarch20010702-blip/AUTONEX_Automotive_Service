import { useContext, useEffect, useState } from "react";

import { EventsContext, type BookingEvent } from "./eventsContext";

// Вынесено из events.tsx (2026-09-18) — см. eventsContext.ts, почему.
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
