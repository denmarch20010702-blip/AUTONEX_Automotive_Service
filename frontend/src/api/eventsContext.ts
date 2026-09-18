import { createContext } from "react";

// Вынесено из events.tsx (2026-09-18, найдено линтером `eslint-plugin-
// react-refresh`): файл, экспортирующий и компонент, и хук/константу разом,
// ломает точечный Vite Fast Refresh — при правке такого файла HMR не может
// найти границу компонента и откатывается на полную перезагрузку страницы
// вместо точечного обновления. `EventsProvider` (компонент) остаётся в
// events.tsx, тип и сам React-контекст — здесь, хуки-потребители — в
// eventHooks.ts. Три файла вместо одного, но каждый Fast-Refresh-безопасен.
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

export const EventsContext = createContext<BookingEvent[]>([]);
